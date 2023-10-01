from pathlib import Path
import sys, socket, io, json

import requests

if not str(Path(__file__).parent) in sys.path:
	sys.path.append(str(Path(__file__).parent))

from jag_util import *

from jag_logging import LogRecord
from jag_exceptions import *
import jag_http_ents

_room_echo = '[Request Evaluator]'

_rebind = print


def echo_exception_to_client(err, con):
	import traceback

	trback = ''.join(
		traceback.format_exception(
			type(err),
			err,
			err.__traceback__
		)
	)

	con.sendall('HTTP/1.1 500 Internal Server Error\r\n'.encode())
	response_content = f"""<!DOCTYPE HTML>
		<html>
			<head>
				<meta http-equiv="Content-Type" content="text/html;charset=utf-8">
				<title>Rejected</title>
			</head>
			<body>
				<h1 style="border-left: 2px #9F2E25;">500 Internal Server Error</h1>
				<h3>Server: Jag</h3>
				<p style="white-space: pre;">{trback}</p>
			</body>
		</html>
	"""
	con.sendall(f'Content-Length: {len(response_content)}\r\n\r\n'.encode())
	con.sendall(response_content.encode())



def _default_room(request, response, services):
	conlog('Executing default action', request.abspath)

	# for this to work it has to be a GET request
	if request.method == 'get':

		# anything that is not inside the server shall get rejected
		if not request.abspath.resolve().is_relative_to(request.srv_res.doc_root):
			request.reject()
			return

		# first check if path explicitly points to a file
		if request.abspath.is_file():
			services.serve_file()
			return

		# if it's not a file - check whether the target dir has an index.html file
		if (request.abspath / 'index.html').is_file():
			services.serve_dir_index()
			return

		# if it's just a directory - list it
		if request.abspath.is_dir() and request.srv_res.cfg['dir_listing']['enabled']:
			services.list_dir()
			return


	# otherwise - reject
	request.reject(405)



# utility class returned by server_timings.record
class PerfRec:
	def __init__(self, sv_timings, msg:str='perftest', _internal:bool=False, noreport:bool=False):
		"""
		- msg:str='perftest'   -> The name of the timing record
		- ms:bool=True         -> Use milliseconds instead of seconds to record timing
		- _internal:bool=False -> Wether the record is coming from jag itself or user
		- noreport:bool=False  -> Don't write down the record
		"""
		self._internal:bool = _internal
		self.noreport:bool = noreport
		self.sv_timings = sv_timings

		# time module
		self.time = sv_timings.time
		# timestamp of the beginning of the record
		self.start = self.time.time()
		# The name of the timing record
		self.msg:str = str(msg)
		# Resulting timings
		self.result:tuple = ('', 0)

	def __enter__(self):
		return self

	def __exit__(self, type, value, traceback):
		mtime = (self.time.time() - self.start) * 1000
		self.result = (self.msg, mtime)

		if not self.noreport:
			if self._internal:
				self.sv_timings.jag_time.append(self.result)
			else:
				self.sv_timings.timings.append(self.result)




class ServerTimings:
	"""
	Various tools for measuring server performance.
	
	Timings are recorded at all times, but Server-Timing API
	has to be explicitly enabled.

	Ideally, the server should respond within ~100ms,
	so try to measure performance in groups and not individual function calls.
	"""
	def __init__(self):
		# time module
		import time
		self.time = time

		# internal timings
		self.jag_time:list = []
		# custom timings
		self.timings:list = []

		# Inclusion of the Server-Timing response header
		self.enable_header:bool = False
		# Whether to include internal Jag timings or not
		self.header_incl_jag:bool = False

	def enable_in_response(self, include_jag_timings:bool=False):
		"""
		Enable 'Server-Timing' header in response.
		The system follows Server-Timing specs.
		- include_jag_timings:bool=False -> whether to include internal Jag timings or not

		It's ok to call this function multiple times.
		"""
		self.enable_header:bool = True
		self.header_incl_jag:bool = include_jag_timings

	def record(
		self,
		msg:str='perftest',
		noreport:bool=False,
		_internal:bool=False
	) -> PerfRec:
		"""
		- msg:str='perftest'   -> The name of the timing record
		- noreport:bool=False  -> Don't write down the record
		"""
		return PerfRec(self, msg, _internal, noreport)

	def push_record(self, record:tuple[str, int|float|str], _internal:bool=False):
		"""
		Manually add an abstract record.
		Format: tuple(message:str, timing:int|float|str)
		"""
		if _internal:
			self.jag_time.append(record)
		else:
			self.timings.append(record)

	def as_header(self, only_value:bool=True) -> str:
		records = []
		for rec in self.jag_time:
			records.append(f'''{rec[0]};dur={rec[1]}''')
		for rec in self.timings:
			records.append(f'''{rec[0]};dur={rec[1]}''')

		if only_value:
			return ', '.join(records)
		else:
			return f"""Server-Timings: {', '.join(records)}"""





class ServerServices:
	"""
	A bunch of default services the server can provide.
	Most notable one: Serving GET requests
	"""
	def __init__(self, request:'ClientRequest', response:'ServerResponse'):
		self.request = request
		self.response = response
		self.srv_res = request.srv_res

	# Serve a file to the client in a CDN manner
	# If no file is provided - serve path from the request
	def serve_file(self, tgt_file=None, respect_range=True, chunked=False, _force_oneflush=False):
		"""
		Serve a file to the client.
		It's possible to specify a target file.
		If no target file is specified, then reuqest path is used.
		- tgt_file:str|pathlike=None -> Path to the file to serve, defaults to request path.
		- respect_range:bool=True    -> Take the "Range" header into account.
		- chunked:bool=False         -> If set to true - use Transfer-Encoding: chunked
		"""
		request = self.request
		response = self.response

		Path = self.srv_res.pylib.Path

		if not tgt_file and not request.abspath.is_file():
			self.request.reject()
			return
		tgt_file = Path(tgt_file or request.abspath)

		# all good - set content type and send the shit
		response.content_type = (
			request.srv_res.mimes['signed'].get(tgt_file.suffix)
			or
			'application/octet-stream'
		)

		# Basically, debugging
		if _force_oneflush:
			response.flush_bytes(tgt_file.read_bytes())
			self.request.terminate()
			return

		# if the size is too big for a single flush - stream in chunks
		# This is very important, because serving a 2kb svg in chunks slows the response time
		# and serving an 18gb .mkv Blu-Ray remux in a single flush is impossible
		if tgt_file.stat().st_size > request.srv_res.cfg['buffers']['max_file_len']:
			with open(str(tgt_file), 'r+b') as f:
				# if request comes with a Range header - try serving the requested byterange
				# '0-' VERY funny, fuck right off
				if request.byterange and (request.headers.get('range', 'bytes=0-').strip() != 'bytes=0-') and respect_range:
					conlog('The client has fucked us over:', request.headers.get('range', '0-').strip())
					response.serve_range(f)
				else:
					# response.stream_buffer(f, (1024*1024)*5)
					response.stream_buffer(
						f,
						chunked=chunked,
						buf_size=self.srv_res.cfg['buffers']['bufstream_chunk_len'],
					)
		else:
			response.flush_bytes(tgt_file.read_bytes())

		self.request.terminate()

	# List directory as an html page
	def list_dir(self):
		"""
		- Set content type to text/html
		- Progressively generate listing for a directory and stream it to the client
		- Close connection
		"""
		from dir_list import dirlist
		lister = dirlist(self.request.srv_res)

		self.response.content_type = 'text/html'

		with self.response.stream_chunks() as stream:
			for chunk in self.request.srv_res.list_dir.dir_as_html(self.request.abspath):
				stream.send(chunk)


	# Serve "index.html" from the requested path
	# according to server config
	def serve_dir_index(self):
		"""
		Serve "index.html" from the requested path
		If the file mentioned above doesn't exist in the dir - reject
		"""
		if not (self.request.abspath / 'index.html').is_file():
			self.request.reject()

		self.response.content_type = 'text/html'
		self.response.flush_bytes(
			(self.request.abspath / 'index.html').read_bytes()
		)

	# Because why not
	def default(self):
		"""
		Execute default stack of actions:
		- if it's a GET request (reject otherwise):
			- If request path is not relative to the doc root - reject
			- If request points to a file - serve it
			- If request points to a directory - list it IF dir listing is enabled
		"""
		_default_room(self.request, self.response, self)







# Stream bytes to the client
class ChunkStreamToClient:
	def __init__(self, request:'ClientRequest', cl_con:socket.socket, self_terminate:bool):
		self.cl_con = cl_con
		self.request = request
		self.auto_term = self_terminate

	def __enter__(self):
		return self

	def __exit__(self, type, value, traceback):
		# todo: does this also has to be hex ?
		self.cl_con.sendall(b'0\r\n\r\n')
		# No auto termination, because it's speculated,
		# that it's possible to send some sort of trailing headers or whatever
		if self.auto_term:
			self.request.terminate()

	def send(self, data):
		# send the chunk size
		self.cl_con.sendall(f"""{hex(len(data)).lstrip('0x')}\r\n""".encode())
		# send the chunk itself
		self.cl_con.sendall(data)
		# send separator
		self.cl_con.sendall(b'\r\n')


class ByteStreamToClient:
	def __init__(self, request:'ClientRequest', cl_con:socket.socket, self_terminate:bool):
		self.request = request
		self.cl_con = cl_con
		self.auto_term = self_terminate

	def __enter__(self):
		return self

	def __exit__(self, type, value, traceback):
		if self.auto_term:
			self.request.terminate()

	def send(self, data:bytes):
		self.cl_con.sendall(data)


# Read part of a buffer in chunks (start:end)
# todo: There are 0 validations
# (neither end or start can be negative)
# (end cannot be smaller than start)
# (start and end cannot be the same)
# (start and end cannot result into 0 bytes read)

# src  -----------------------
# rng        ^         ^      
# prog       -----            
# want            ---------   
# let             ------      

# RANGES ARE INCLUSIVE FROM BOTH SIDES IN HTTP !
class AlignedBufReader:
	def __init__(self, buf, start, end):
		# START is inclusive
		# END is NOT inclusive
		self.buf = buf
		self.start = start
		self.end = end
		self.target_amount = end - start
		self.progress = 0

		# seek to the beginning
		self.buf.seek(start, 0)

	def read(self, amt):
		# max(smallest, min(n, largest))
		# Todo: is this slow ?
		allowed_amount = max(0, min(amt, self.end - self.progress))
		chunk = self.buf.read(allowed_amount)
		self.progress += allowed_amount
		return chunk


class ServerResponse:
	def __init__(self, request:'ClientRequest', cl_con:socket.socket, srv_res):
		self.request:'ClientRequest' = request
		self.cl_con:socket.socket = cl_con
		self.srv_res = srv_res
		self.timings:ServerTimings = self.request.timings
		self.headers:jag_http_ents.HTTPHeaders = jag_http_ents.HTTPHeaders({
			'Server': 'Jag',
			# 'Server-Timings': '',
		})

		self.content_type:str = 'application/octet-stream'
		self.code:int = 200

		self.offered_services:ServerServices = ServerServices(self.request, self)

	# Dump headers and response code to the client
	def send_preflight(self):
		"""
		Dump headers and response code to the client
		"""

		# send response code
		self.cl_con.sendall(
			f"""HTTP/1.1 {self.srv_res.response_codes.get(self.code, self.code)}\r\n""".encode()
		)

		# important todo: better way of achieving this
		self.headers['Content-Type'] = self.content_type

		if self.timings.enable_header:
			self.headers['Server-Timing'] = self.timings.as_header()

		# send headers
		for hbytes in self.headers.progrssive_construct():
			self.cl_con.sendall(hbytes)

		# Send an extra \r\n to indicate the end of headers
		self.cl_con.sendall('\r\n'.encode())

		# important todo: There's a built-in way to make functions only fire once
		# Yes, BUT, it costs A LOT of time and effort for the machine
		# Such a simple buttplug is WAY more efficient
		self.send_preflight = lambda: None

	def send_headers_only(self):
		self.code = 204
		self.send_preflight()
		self.request.terminate()

	def mark_as_xfiles(self, filename):
		"""
		This is needed if you want the response body to be treated
		as a file download by the client.
		Useful when a media file, like .mp4 video should be downloaded
		by the client instead of playing back.

		Keep in mind this simply
		adds a header to the response. It's up to the client to decide
		what to do with it.
		(all modern browsers do the right thing)
		"""
		del self.headers['Content-Disposition']
		self.headers['Content-Disposition'] = f'attachment; filename="{str(filename)}"'

	def set_filename(self, filename):
		"""
		Give content a name, but not mark it for download.

		Keep in mind this simply
		adds a header to the response. It's up to the client to decide
		what to do with it.
		(all modern browsers do the right thing)
		"""
		del self.headers['Content-Disposition']
		self.headers['Content-Disposition'] = f'filename="{str(filename)}"'

	# - Send headers to the client
	# - Send the entirety of the provided bytes in one go
	# - Collapse connection
	def flush_bytes(self, data):
		if not isinstance(data, bytes):
			raise TypeError(f'data must be of type bytes, not {type(data)}')

		# important todo: the response should either be chunked or have Content-Length header
		self.headers['Content-Length'] = len(data)

		# send headers
		self.send_preflight()

		# send the body
		self.cl_con.sendall(data)

		# terminate
		self.request.terminate()


	def flush_json(
		self,
		jdata:tuple|list|dict|set,
		bytes_to_array:bool=False,
		set_header:bool=True,
		autoconvert:bool=False
	):
		"""
		Same as flush_bytes, except this function takes dictionaries as an input.
		Sets Content-Type header to 'application/json'
		This function also automatically encodes some commonly used types, such as:

		- pathlib > str
		- complex > tuple(c.real, c.imag)
		- bytes > list[int]
		"""
		libs = self.srv_res.pylib

		# todo: use dicts to determine types
		# todo: move this to util ?
		def complex_encoder(obj):
			if isinstance(obj, libs.Path):
				return str(obj)
			elif isinstance(obj, complex):
				return obj.real, obj.imag
			elif isinstance(obj, bytes) and bytes_to_array:
				return list(obj)
			else:
				raise TypeError(f"""Object of type {obj.__class__.__name__} is not serializable""")

		if set_header:
			self.content_type = 'application/json'

		if autoconvert:
			self.flush_bytes(
				libs.json.dumps(jdata, default=complex_encoder).encode()
			)
		else:
			self.flush_bytes(
				libs.json.dumps(jdata).encode()
			)


	def stream_chunks(self, self_terminate=True):
		"""
		Stream byte data to the client in HTTP chunks:

		- set 'Transfer-Encoding' header to 'chunked'
		- Dump headers
		- Start streaming chunks:

			- This returns an object for use with "with" keyword.
			- The object only has 1 method: send(),
			  which only takes 1 argument: Bytes to send

		Example::

		    with response.stream_chunks() as stream:
		        for data in whatever:
		            stream.send(data)
		"""

		self.headers['Transfer-Encoding'] = 'chunked'

		# It's impossible to stream multiple groups of chunks
		self.send_preflight()

		return ChunkStreamToClient(self.request, self.cl_con, self_terminate)


	def stream_bytes(self, length:int, self_terminate:bool=True):
		"""\
		Gradually stream bytes to the client with known payload length.
		Useful for keeping track of the amount of data sent.

		- Set Content-Length header.
		- Start streaming bytes.

		Example::

		    with response.stream_bytes(some_buf.seek(0, 2)) as stream:
		        some_buf.seek(0, 0)
		        while True:
		            data = some_buf.read(4096)
		            if not data:
		                break
		            stream.send(data)
		"""
		self.headers['Content-Length'] = length
		self.send_preflight()
		return ByteStreamToClient(self.request, self.cl_con, self_terminate)


	def stream_buffer(self, tgt_buf, chunked:bool=False, buf_size:int=None):
		"""\
		Automatically stream a buffer to the client in small chunks.

		    chunked=False: Seek to the end of the buffer to
		determine its length, set Content-Length header
		and gradually stream the buffer.

		    chunked=True: Don't seek the buffer, set Transfer-Encoding
		to 'chunked' and stream the buffer while there's data to be read.
		"""
		clen = None

		# The response is EITHER chunked OR has Content-Length
		if chunked:
			self.headers['Transfer-Encoding'] = 'chunked'
		else:
			clen = tgt_buf.seek(0, 2)

		# first - dump headers
		# self.send_preflight()

		# Move the carret to the very beginning of the buffer
		tgt_buf.seek(0, 0)
		# stream chunks
		with self.stream_chunks(content_length=clen) as stream:
			while True:
				# read chunk
				chunk = tgt_buf.read(
					buf_size or self.srv_res.cfg['buffers']['bufstream_chunk_len']
				)
				# check if there's still any data
				if not chunk:
					break
				stream.send(chunk)


	# Serve specified buffer according to the Range header
	# important todo: This is 100% raw/bare, basically experimental
	# nothing is checked or validated
	def serve_range(self, buf):
		# Set code to partial-content
		self.code = 206
		# It'd be stupid not to do it this way...
		self.headers['Transfer-Encoding'] = 'chunked'
		self.send_preflight()

		buf_size = buf.seek(0, 2)

		# begin streaming
		with self.stream_chunks() as stream:
			# stream all chunk groups
			# (order is preserved)
			for chunk_start, chunk_end in self.request.byterange:
				# Python is amazing: array[37:None] is a valid syntax
				_start = chunk_start
				_end = chunk_end or buf_size

				conlog('Serving partial content', self.request.byterange, _start, _end)

				# If only end is specified - stream suffix
				# Todo: current implementation requires calculating
				# start offset, which means that buffer should be of known size
				if chunk_end and not chunk_start:
					_end = buf_size
					_start = _end - chunk_end

				aligned_reader = AlignedBufReader(buf, _start, _end)
				while True:
					data = aligned_reader.read(self.srv_res.cfg['buffers']['bufstream_chunk_len'])
					if not data:
						break
					stream.send(data)



class HeaderFields:
	"""
	Collect header fields from a client connection.
	First initialize the class and then call collect() function
	    - cl_con - client connection.
	    - maxsize - max size of the header fields in bytes
	It's impossible to "stream" the header fields, because it's stupid.
	If the field exceeds the max size - the client can basically fuck off.
	"""
	def __init__(self, cl_con:socket.socket, maxsize:int=65535):
		self.cl_con:socket.socket = cl_con
		self.maxsize:int =          maxsize
		self.lines:list  =          []

		# This is probably only needed for reading forms,
		# but might be handy for other things too.

		# This variable stores an exact amount of bytes
		# this class has read from the socket.
		self.data_read_size:int = 0

	def collect(self):
		"""
		Collect the header fields as lines into self.lines
		"""
		maxsize = self.maxsize

		# Mega important shit: not setting buffering to 0 would result into
		# extra data being buffered even AFTER the fields end
		rfile = self.cl_con.makefile('rb', newline=b'\r\n', buffering=0)
		conlog('created virtual file')
		with DynamicGroupedText('Read Header Fields Stream') as log_group:
			while True:
				if maxsize <= 0:
					# self.reject(431)
					# is this ok ?
					# return False
					# todo: this should log a warning or maybe even error
					break
				line = rfile.readline(maxsize)
				log_group.print('read line', line)

				# it's important to also count \r\n\t etc.
				maxsize -= len(line)
				self.data_read_size += len(line)

				# encountered end of the header fields
				if line == b'\r\n':
					log_group.print('Encountered fields end', line)
					self.data_read_size += 2
					break

				# append field to the buffer
				# todo: is this strip() really ok ?
				self.lines.append(line.decode().strip())

			rfile.close()


# ==================================
#           Body Readers
# ==================================

class BodyByteStreamReader:
	"""Low-level progressive body byte reader"""
	def __init__(self, request:'ClientRequest', response:ServerResponse, total_length:int=0):
		self.request:'ClientRequest' = request
		self.response:ServerResponse = response
		self.total_length:int = total_length
		self.progress:int = 0
		self.socket_file = self.request.cl_con.makefile('rb', buffering=0)

	def __enter__(self):
		return self

	def __exit__(self, type, value, traceback):
		self.socket_file.close()

	def read(self, amount:int=4096):
		# todo: is it ok to read 0 bytes from the socket file ?

		allowance = amount
		if self.total_length:
			if self.total_length >= self.progress:
				return b''
			allowance = clamp(amount, 0, self.total_length - self.progress)

		chunk = self.socket_file.read(allowance)
		self.progress += allowance
		return chunk


class MultipartFormField:
	def __init__(self, request:'ClientRequest', response:ServerResponse):
		self.request = request
		self.response = response
		self.cl_con = request.cl_con





class MultipartFormReader:
	"""\
	Read a request encoded with multipart/form-data
	"""
	def __init__(self, request:'ClientRequest', response:ServerResponse):
		self.request = request
		self.response = response
		self.cl_con = request.cl_con

		self.boundary:str = jag_http_ents.HTTPHeaderKV(
			self.request.headers['content-type']
		)['boundary']

		if not self.boundary:
			raise InvalidFormData(
				'Invalid Multipart Form data: No boundary present'
			)

		self.boundary = self.boundary.encode()


	def __enter__(self):
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		pass

	def next_field(self) -> MultipartFormField:
		"""\
		Traverse to the next field,
		skipping the previous one if it wasn't read.
		"""




class URLEFormField:
	"""\
	URL-encoded form field.
	Works the same as multipart form field for
	consistency.
	"""

	# field name
	name:str = None
	# field type: file/text/...
	type:str = None
	# The name of the file, if any
	filename:str = None
	# Content-Disposition: form-data
	disposition:str = None

	def __init__(self, request:'ClientRequest', fname:str):
		self.request = request
		self.cl_con = request.cl_con

		self.name = fname

	def read_value(self):
		# important todo: this is TOO slow
		self.name = 'ded'


class URLEFormReader:
	"""\
	Content-Type: application/x-www-form-urlencoded
	field1=value1&field2=value2

	    This is pretty much useless, because there'd never be so much data
	for there to be a need to read it as a stream...

	    This behaviour is only needed for consistency with
	multipart/form-data;boundary="boundary" type of messages.
	"""

	# This is only needed to prevent malicious requests
	kname_maxsize:int = 65535
	kval_maxsize:int = 65535
	# field1=value1&field2=value2
	def __init__(
		self,
		request:'ClientRequest',
		response:ServerResponse,
	):
		self.request = request
		self.response = response
		self.cl_con = request.cl_con

		self.overflow = io.BytesIO()

	def __enter__(self):
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		pass

	def next_field(self) -> URLEFormField:
		"""\
		Traverses to the next field,
		skipping the previous one if it wasn't read.
		"""





class ProgressiveBodyReader:
	"""\
	Read the body stream progressively.
	"""
	def __init__(self, request:'ClientRequest', response:ServerResponse):
		self.request:'ClientRequest' = request
		self.response:ServerResponse = response

	def read_bytestream(self, no_length_ok:bool=False, autoreject:bool=True):
		"""\
		Progressively read bytes from the body.
		You should be very skeptical about POST requests without
		Content-Length...
		"""

		content_length = self.request.headers.get('content-length') or 0

		if not content_length and not no_length_ok:
			if autoreject:
				self.request.reject(411)
			raise MissingContentLength('The client did not provide mandatory Content-Length header')

		return BodyByteStreamReader(self.request, self.response, content_length)


	def read_form(self, autoreject:bool=True, kname_maxsize:int=None, kval_maxsize:int=None):
		"""\
		Read form data as stream.
		Both x-www-form-urlencoded and multipart/form-data are supported.

		Both behave the same.
		"""
		pass


class InstantBodyReader:
	"""\
	Wrapper around ProgressiveBodyReader.
	Does the same, but reads the entire stream in one go.
	"""
	def __init__(self, request:'ClientRequest', response:ServerResponse):
		self.request:'ClientRequest' = request
		self.response:ServerResponse = response
		self.progressive_reader = ProgressiveBodyReader(request, response)


class ClientRequestBodyReader:
	"""\
	A collection of ways ro read the request body.
	Supported reading formats:
	    - Simple onepiece requests, like POST requests with regular jsons and Content-Length header
	    - Streams without Content-Length header
	    - Multipart requests
	"""
	def __init__(self, request:'ClientRequest', response:ServerResponse):
		self.progressive_reader:ProgressiveBodyReader = ProgressiveBodyReader(request, response)
		self.instant_reader:InstantBodyReader =         InstantBodyReader(request, response)


# important todo: easy OPTIONS negotiation controls
class ClientRequest:
	def __init__(self, cl_con:socket.socket, cl_addr:tuple[str, int], srv_res, timing_api):
		self.cl_con =  cl_con
		self.cl_addr = cl_addr
		self.srv_res = srv_res
		self.timings = timing_api

		# Keep track of request termination
		# For instance, request may be terminated while collecting header fields
		self.terminated:bool = False

		# create empty storage for header fields
		self.headers:jag_http_ents.HTTPHeaders = jag_http_ents.HTTPHeaders()

		# Initialize the response class
		# Early init of this class is needed
		# for rejecting certain requests
		with self.timings.record('rsp_class_init', _internal=True):
			self.response = ServerResponse(self, cl_con, srv_res)

		self._byterange = None

		# Try/Except in case of malformed request
		# Why bother?
		# It's client's responsibility to perform good requests
		try:
			self.eval_request()
		except Exception as e:
			self.reject(400)
			conlog(traceback_to_text(e))
			# raise e

		# now that the request is evaluated - create a body reader class
		self.body_reader:ClientRequestBodyReader = ClientRequestBodyReader(self, self.response)
		

	# Init
	# =================

	# Request evaluation is a dedicated function for easier error handling
	def eval_request(self):
		# io = self.srv_res.pylib.io
		# sys = self.srv_res.pylib.sys
		urllib = self.srv_res.pylib.urllib
		Path = self.srv_res.pylib.Path

		# Fully custom method of receiving the Request Header
		# gives a lot of benefits (as well as causing mental retardation)
		with self.timings.record('collect_hbuf', _internal=True):
			header_buffer = HeaderFields(self.cl_con, self.srv_res.cfg['buffers']['max_header_len'])
			header_buffer.collect()


		with self.timings.record('eval_hbuf', _internal=True):
			header_fields = header_buffer.lines
			conlog(iterable_to_grouped_text(header_fields, 'Decoded Header Fields'))

			# First line of the header is always [>request method< >path< >http version<]
			# It's up to the client to send valid data
			self.method, self.path, self.protocol = header_fields[0].split(' ')
			conlog(iterable_to_grouped_text((self.method, self.path, self.protocol), 'Top Field'))
			self.method = self.method.lower()

			# deconstruct the url into components
			parsed_url = urllib.parse.urlparse(self.path)

			# important todo: lazy processing
			# first - evaluate query params
			self.query_params = {k:(''.join(v)) for (k,v) in urllib.parse.parse_qs(parsed_url.query, True).items()}
			conlog(iterable_to_grouped_text(self.query_params, 'Url params:'))

			# then, evaluate path
			decoded_url_path = urllib.parse.unquote(parsed_url.path)
			self.abspath = self.srv_res.doc_root / Path(decoded_url_path.lstrip('/'))
			self.relpath = Path(decoded_url_path.lstrip('/'))
			self.trimpath = decoded_url_path

			# Delete the first line as it's no longer needed
			del header_fields[0]

			# get remaining headers
			self.headers = jag_http_ents.HTTPHeaders(header_fields)

			# init cookies
			self.cookies = jag_http_ents.Cookies(self.headers, self.response.headers)

			conlog(iterable_to_grouped_text(self.headers.fields, 'Request headers:'))
			conlog(iterable_to_grouped_text(self.cookies.request_cookies.kv_dict, 'Cookies:'))



		# WSS
		# todo: does this really belong here ?
		if str(self.headers['upgrade']).lower() == 'websocket':
			if self.srv_res.cfg['websockets']['action'] == 'reject':
				self.reject(403)
				return

			if self.srv_res.cfg['websockets']['action'] == 'redirect':
				self.redirect(self.srv_res.cfg['websockets']['redirect_to'])
				return

			if self.srv_res.cfg['websockets']['action'] == 'accept':
				# important todo: because this is not a wss server
				self.reject(421)
				return

		# make sure this function doesn't trigger twice
		self.eval_request = lambda: None



	# Actions
	# =================

	# Properly collapse the tunnel between server and client
	def terminate(self):
		# socket = self.srv_res.pylib.socket
		self.cl_con.shutdown(socket.SHUT_RDWR)
		self.cl_con.close()
		self.terminated = True
		# Termination is only possible once
		self.terminate = lambda: None

	# Send a very simple html document
	# with a short description of the provided Status Code
	def reject(self, code:int=401, hint:str=''):
		self.response.code = code
		self.response.content_type = 'text/html'
		self.response.flush_bytes(
			self.srv_res.reject_precache
			.replace(b'$$reason', self.srv_res.response_codes.get(code, f'{code} ERROR').encode())
			.replace(b'$$hint', str(hint).encode())
		)

	# Send a redirection response (codes 300)
	def redirect(self, target, reason:int=7, softlink:bool=False):
		"""
		Redirect the request to the target destination.

		- target: target URL to redirect to
		- reason: 0-8 (300, 301, 302...), default to 7 (307)
		- softlink: False = Location. True = Content-Location
		"""
		# self.srv_res.response_codes.get
		reason_picker = {code:(300+code) for code in range(7)}
		self.response.code = reason_picker.get(reason, 307)
		self.response.headers['Location' if softlink else 'Content-Location'] = str(target)

		self.response.send_preflight()
		self.terminate()

	def read_body_bytes(
		self,
		as_buf:bool=False,
		maxsize:int|None=None,
		no_length_ok:bool=True,
		autoreject:bool=True,
	) -> bytes|io.BytesIO:
		"""
		Read the entire request body in one go as bytes or buffer.
		This is a handy wrapper around ClientRequestBodyReader.

		:param as_buf:
			Set this to True to return the body as BytesIO
			instead of raw bytes.
		:param maxsize:
			Restrict the size of the body to n bytes
		:param no_length_ok:
			Whether to reject requests that come without Content-Length header.
			See autoreject for more.
		:param autoreject:
			Setting this to True would automatically reject the request in case of
			client-side errors with corresponding rejection code.
			Otherwise an exception is raised.
		"""
		buf = self.srv_res.pylib.io.BytesIO()

		with self.body_reader.progressive_reader.read_bytestream(no_length_ok, autoreject) as stream:
			while True:
				chunk = stream.read(4096)
				if not chunk:
					break
				buf.write(chunk)
				if maxsize and buf.tell() > maxsize:
					self.reject(413)
					raise PayloadTooLarge(f'The received payload ({buf.tell()}) exceeds the limit ({maxsize})')

		if as_buf:
			buf.seek(0, 0)
			return buf
		else:
			return buf.getvalue()

	def read_body_json(
		self,
		maxsize:int|None=None,
		no_length_ok:bool=False,
		autoreject:bool=True,
	) -> dict|list:
		"""\
		Read request body as json. Same params as for read_body_bytes,
		except for as_buf, because resulting json cannot be a buffer
		"""

		try:
			return json.loads(
				self.read_body_bytes(False, maxsize, no_length_ok, autoreject)
			)
		except json.JSONDecodeError as e:
			if autoreject:
				self.reject(422, 'Bad JSON')
			else:
				raise e


	# Processed headers
	# =================

	# A client may ask for an access to a specific chunk of the target file.
	# In this case a "Range" header is present.
	# It has a format of start-end (both inclusive)
	# This function returns an evaluated tuple from the following header.
	# If "Range" header is not present - None is returned.
	# Tuple format is as follows: (int|None, int|None)
	# Negative numbers are clamped to 0
	# important todo: byterange should be a class
	@property
	def byterange(self):
		if self._byterange:
			return self._byterange

		range_data = self.headers.get('range')
		if not range_data:
			return None

		# todo: it's always assumed that range is in bytes
		ranges = range_data.split('=')[1].split(',')

		self._byterange = []
		for chunk in ranges:
			chunk_split = chunk.strip().split('-')
			rstart = max(int(chunk_split[0]) - 1, 0) if chunk_split[0] else None
			rend =   max(int(chunk_split[1]) - 1, 0) if chunk_split[1] else None
			self._byterange.append(
				(rstart, rend)
			)

		return self._byterange



class JagServerIndex:
	"""\
	This class is simply a collection of various resources,
	such as server services, timing API and so on.
	"""
	services:ServerServices = None
	web_timing_api:ServerTimings = None
	pylib_cache = None
	context = None
	internal_log = None




# The server creates "rooms" for every incoming connection.
# The Base Room does some setup, like evaluating the request.
# Further actions depend on the server setup:
# If callback function is specified, then it's triggered
# without any automatic actions
# If callback function is NOT specified, then server provides
# Some of its default services

# Yes, this is a function, not a class. Cry
def htsession(cl_con, cl_addr, srv_res, route_index=None):
	import time
	from easy_timings.mstime import perftest

	try:
		# ----------------
		# Setup
		# ----------------

		# Init timings
		timing_api = ServerTimings()

		# the amount of time it took to initialize this worker
		timing_api.push_record(
			('devtime', (time.time() - srv_res.devtime)*1000),
			_internal=True
		)

		# todo: Shouldn't the timing class take this as an argument?
		if srv_res.cfg['enable_web_timing_api']:
			timing_api.enable_in_response(True)

		request_log = {
			'time': srv_res.pylib.datetime.datetime.now(),
		}


		# ----------------
		# Eval request
		# ----------------
		with timing_api.record('rq_eval', _internal=True):
			evaluated_request = ClientRequest(cl_con, cl_addr, srv_res, timing_api)
			response = evaluated_request.response

		conlog('Initialized basic room, evaluated request')

		# sometimes the connection may be aborted earlier by the client
		if evaluated_request.terminated:
			raise ConnectionAbortedError('Connection was aborted early by the client')


		# ----------------
		# Automatic actions
		# ----------------
		route_info = route_index.match_route('/' + evaluated_request.relpath.as_posix(), evaluated_request.method)

		if route_info == 'invalid_method':
			conlog('Room: invalid method:', evaluated_request.method)
			evaluated_request.reject(405)

		# Treat options
		if evaluated_request.method == 'options':
			access_ctrl = route_info.access_ctrl(evaluated_request.headers, response.headers)
			access_ctrl.apply_headers()
			response.headers['Access-Control-Allow-Methods'] = (', '.join(route_info.methods)).upper()
			response.send_headers_only()


		# ----------------
		# Execute action
		# ----------------

		# handy (maybe) index
		server_index = JagServerIndex()
		server_index.services = evaluated_request.response.offered_services
		server_index.web_timing_api = timing_api
		server_index.pylib_cache = evaluated_request.srv_res.pylib

		# Now either pass the control to the room specified in the config
		# or the default room
		if not evaluated_request.terminated:
			route_info.func(
				evaluated_request,
				evaluated_request.response,
				server_index
			)



		# ----------------
		# Write Log
		# ----------------
		with perftest('Room logging took'):
			ev_rq = evaluated_request

			# connection log
			upd_rec_data = {
				'addr_info': ev_rq.cl_addr,
				'method': ev_rq.method,
				'httpver': ev_rq.protocol,
				'path': ev_rq.trimpath,
				'usragent': ev_rq.headers['user-agent'],
				'ref': ev_rq.headers['referer'],
				'rsp_code': ev_rq.response.code,
			}

			# create log record class
			lrec = LogRecord(1, request_log | upd_rec_data)
			# send record to the logging server
			lrec.push()


	except ConnectionAbortedError as err:
		conlog('Connection was aborted by the client')
	except ConnectionResetError as err:
		conlog('Connection was reset by the client')
	except Exception as err:
		import traceback, sys

		conlog(
			''.join(
				traceback.format_exception(
					type(err),
					err,
					err.__traceback__
				)
			)
		)

		try:
			if srv_res.cfg['errors']['echo_to_client']:
				echo_exception_to_client(err, cl_con)
			err_rec = LogRecord(2, traceback_to_text(err))
			err_rec.push()
		except Exception as e:
			pass

		sys.exit()


	import sys
	# conlog('        Exiting...', evaluated_request.cl_addr[1])
	# _rebind('Exiting...')
	# cl_con.shutdown(2)
	cl_con.close()
	sys.exit()

