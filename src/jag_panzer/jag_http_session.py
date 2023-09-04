from pathlib import Path
import sys

if not str(Path(__file__).parent) in sys.path:
	sys.path.append(str(Path(__file__).parent))

from jag_util import dict_pretty_print, print_exception, traceback_to_text, conlog, iterable_to_grouped_text, DynamicGroupedText

from jag_logging import logRecord
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
class perfrec:
	def __init__(self, sv_timings, msg='perftest', _internal=False, noreport=False):
		"""
		- msg:str='perftest'   -> The name of the timing record
		- ms:bool=True         -> Use milliseconds instead of seconds to record timing
		- _internal:bool=False -> Wether the record is coming from jag itself or user
		- noreport:bool=False  -> Don't write down the record
		"""
		self._internal = _internal
		self.noreport = noreport
		self.sv_timings = sv_timings

		# time module
		self.time = sv_timings.time
		# timestamp of the beginning of the record
		self.start = self.time.time()
		# The name of the timing record
		self.msg = msg
		# Resulting timings
		self.result = ('', 0)

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




class server_timings:
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
		self.jag_time = []
		# custom timings
		self.timings = []

		# Inclusion of the Server-Timing response header
		self.enable_header = False
		# Whether to include internal Jag timings or not
		self.header_incl_jag = False


	def enable_in_response(self, include_jag_timings=False):
		"""
		Enable 'Server-Timing' header in response.
		The system follows Server-Timing specs.
		- include_jag_timings:bool=False -> whether to include internal Jag timings or not

		It's ok to call this function multiple times.
		"""
		self.enable_header = True
		self.header_incl_jag = include_jag_timings


	def record(self, msg='perftest', noreport=False, _internal=False):
		"""
		- msg:str='perftest'   -> The name of the timing record
		- noreport:bool=False  -> Don't write down the record
		"""
		return perfrec(self, msg, _internal, noreport)


	def push_record(self, record, _internal=False):
		"""
		Manually add an abstract record.
		Format: tuple(message:str, timing:int|float|str)
		"""
		if _internal:
			self.jag_time.append(record)
		else:
			self.timings.append(record)


	def as_header(self, only_value=True):
		records = []
		for rec in self.jag_time:
			records.append(f'''{rec[0]};dur={rec[1]}''')
		for rec in self.timings:
			records.append(f'''{rec[0]};dur={rec[1]}''')

		if only_value:
			return ', '.join(records)
		else:
			return f"""Server-Timings: {', '.join(records)}"""





class sv_services:
	"""
	A bunch of default services the server can provide.
	Most notable one: Serving GET requests
	"""
	def __init__(self, request, response):
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
			response.flush_buffer(tgt_file.read_bytes())
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
			response.flush_buffer(tgt_file.read_bytes())

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

		with self.response.stream_bytes() as stream:
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
		self.response.flush_buffer(
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







# Stream chunks
class _chunkstream:
	def __init__(self, request, cl_con, self_terminate, non_chunked=False):
		self.cl_con = cl_con
		self.request = request
		self.auto_term = self_terminate
		self.non_chunked = non_chunked

	def __enter__(self):
		return self

	def __exit__(self, type, value, traceback):
		if not self.non_chunked:
			self.cl_con.sendall(b'0\r\n\r\n')
		# No auto termination, because it's speculated,
		# that it's possible to send some sort of trailing headers or whatever
		if self.auto_term:
			self.request.terminate()

	def send(self, data):
		# send the chunk size
		if not self.non_chunked:
			self.cl_con.sendall(f"""{hex(len(data)).lstrip('0x')}\r\n""".encode())
		# send the chunk itself
		self.cl_con.sendall(data)
		# send separator
		if not self.non_chunked: 
			self.cl_con.sendall(b'\r\n')




# Read part of a buffer in chunks (start:end)
# todo: There are 0 validations
# (neither end or start can be negative)
# (end cannot be smaller than start)
# (start and end cannot be the same)
# (start and end should not result into 0 bytes read)

# src  -----------------------
# rng        ^         ^      
# prog       -----            
# want            ---------   
# let             ------      

# RANGES ARE INCLUSIVE FROM BOTH SIDES IN HTTP !
class aligned_buf_read:
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




class sv_response:
	def __init__(self, request, cl_con, srv_res):
		self.request = request
		self.cl_con = cl_con
		self.srv_res = srv_res
		self.timings = self.request.timings
		self.headers = jag_http_ents.HTTPHeaders({
			'Server': 'Jag',
			# 'Server-Timings': '',
		})

		self.add_cookies = []

		self.content_type = 'application/octet-stream'
		self.code = 200

		self.offered_services = sv_services(self.request, self)

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


	# mark response as a download
	def mark_as_xfiles(self, filename):
		"""
		This is needed if you want the response body to be treated
		as a file download by the client.
		Useful when a media file, like .mp4 video should be downloaded
		by the client instead of playing back.
		"""
		self.headers['Content-Disposition'] = f'attachment; filename="{str(filename)}"'

	def set_filename(self, filename):
		"""
		Give content a name, but not mark it for download.
		"""
		self.headers['Content-Disposition'] = f'filename="{str(filename)}"'

	# - Send headers to the client
	# - Send the entirety of the provided buffer/bytes in one go
	# - Collapse connection
	def flush_buffer(self, data):
		if not isinstance(data, bytes):
			data = data.getvalue()

		# important todo: the response should either be chunked or have Content-Length header
		self.headers['Content-Length'] = len(data)

		# send headers
		self.send_preflight()

		# send the body
		self.cl_con.sendall(data)

		# terminate
		self.request.terminate()


	def flush_json(self, jdata, bytes_to_array=False):
		"""
		Same as flush_buffer, except this function takes dictionaries as an input.
		Sets Content-Type header to 'application/json'
		This function also automatically encodes some commonly used types, such as:
		pathlib > str
		complex > tuple(c.real, c.imag)
		"""
		libs = self.srv_res.pylib
		json = libs.json

		# todo: use dicts to determine types
		def complex_encoder(obj):
			if isinstance(obj, libs.Path):
				return str(obj)
			elif isinstance(obj, complex):
				return (obj.real, obj.imag)
			else:
				raise TypeError(f"""Object of type {obj.__class__.__name__} is not serializable""")

		self.content_type = 'application/json'
		self.flush_buffer(
			json.dumps(jdata, default=complex_encoder).encode()
		)


	def stream_bytes(self, content_length=None, self_terminate=True):
		"""
		Stream data to the client in HTTP chunks:
		- set 'Transfer-Encoding' header to 'chunked' IF content_length is none
		- Dump headers
		- Start streaming chunks:
			- This returns an object for use with "with" keyword.
			- The object only has 1 method: send()
			  Which only takes 1 argument: Bytes to send
		"""

		# This cannot be otherwise
		if not content_length:
			self.headers['Transfer-Encoding'] = 'chunked'
		else:
			self.headers['Content-Length'] = content_length

		# It's impossible to stream multiple groups of chunks
		self.send_preflight()

		return _chunkstream(self.request, self.cl_con, self_terminate, not not content_length)


	# Automated action:
	# - Add 'Transfer-Encoding: chunked' header
	# - Send headers to the client
	# - Stream the entirety of the provided buffer in chunks
	# - Collapse the connection
	def stream_buffer(self, data, chunked=False, buf_size=None):
		"""
		Send the data in chunks.
		data = io.BytesIO object.
		buf_size = the size of a single chunk in bytes, default to server config
		Example usage: Pass buffer of an open file to stream it to the client.
		"""
		clen = None

		# The response is EITHER chunked OR has Content-Length
		if chunked:
			self.headers['Transfer-Encoding'] = 'chunked'
		else:
			clen = data.seek(0, 2)

		# first - dump headers
		# self.send_preflight()

		# Move the carret to the very beginning of the buffer
		data.seek(0, 0)
		# stream chunks
		with self.stream_bytes(content_length=clen) as stream:
			while True:
				# read chunk
				chunk = data.read(
					buf_size or self.srv_res.cfg['buffers']['bufstream_chunk_len']
				)
				# check if there's still any data
				if not chunk:
					break
				stream.send(chunk)


	# Serve specified buffer according to the Range header
	# important todo: This is 100% raw/bare
	# nothing is checked or validated
	def serve_range(self, buf):
		# Set code to partial-content
		self.code = 206
		# It'd be stupid not to do it this way...
		self.headers['Transfer-Encoding'] = 'chunked'
		self.send_preflight()

		buf_size = buf.seek(0, 2)

		# begin streaming
		with self.stream_bytes() as stream:
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

				aligned_reader = aligned_buf_read(buf, _start, _end)
				while True:
					data = aligned_reader.read(self.srv_res.cfg['buffers']['bufstream_chunk_len'])
					if not data:
						break
					stream.send(data)



# This is a very risky move
class headerFields:
	"""
	- cl_con - client connection.
	- maxsize - max size of the header fields in bytes
	"""
	def __init__(self, cl_con, maxsize=65535):
		self.cl_con = cl_con
		self.maxsize = maxsize
		self.lines = []

	def collect(self):
		maxsize = self.maxsize

		# Mega important shit: not setting buffering to 0 would result into
		# extra data being buffered even AFTER the fields end\
		rfile = self.cl_con.makefile('rb', newline=b'\r\n', buffering=0)
		conlog('created virtual file')
		with DynamicGroupedText('Read Header Fields Stream') as log_group:
			while True:
				if maxsize <= 0:
					# self.reject(431)
					# is this ok ?
					# return False
					break
				line = rfile.readline(maxsize)
				log_group.print('read line', line)

				# it's important to also count \r\n\t etc.
				maxsize -= len(line)

				# encountered end of the header fields
				if line == b'\r\n':
					log_group.print('Encountered fields end', line)
					break

				# append field to the buffer
				self.lines.append(line.decode().strip())

			rfile.close()




class MultipartPartition:
	"""
	Single partition of a multipart message
	"""
	def __init__(self, request):
		super(MultipartPartition, self).__init__()
		self.arg = arg
		


class MultipartReader:
	"""
	Read a request encoded with multipart/form-data
	"""
	def __init__(self, request):
		self.request = request
		self.cl_con = request.cl_con
		
	def __enter__(self):
		return self

	def __exit__(self, type, value, traceback):
		pass

	def read_all(self, maxsize=None)




# important todo: easy OPTIONS negotiation controls
# sex
class cl_request:
	def __init__(self, cl_con, cl_addr, srv_res, timing_api):
		self.cl_con = cl_con
		self.cl_addr = cl_addr
		self.srv_res = srv_res
		self.timings = timing_api

		self.terminated = False

		self.headers = jag_http_ents.HTTPHeaders()

		# Inficates that the message is multipart
		self.multipart = False;

		# Initialize the response class
		# Early init of this class is needed
		# for rejecting certain requests
		with self.timings.record('rsp_class_init', _internal=True):
			self.response = sv_response(self, cl_con, srv_res)

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
		

	# Init
	# =================

	# Request evaluation has a dedicated function for easier error handling
	def eval_request(self):
		# io = self.srv_res.pylib.io
		# sys = self.srv_res.pylib.sys
		urllib = self.srv_res.pylib.urllib
		Path = self.srv_res.pylib.Path

		# Fully custom method of receiving the Request Header
		# gives a lot of benefits (as well as causing mental retardation)
		with self.timings.record('collect_hbuf', _internal=True):
			header_buffer = headerFields(self.cl_con, self.srv_res.cfg['buffers']['max_header_len'])
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
		socket = self.srv_res.pylib.socket
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
		self.response.flush_buffer(
			self.srv_res.reject_precache
			.replace(b'$$reason', self.srv_res.response_codes.get(code, f'{code} ERROR').encode())
			.replace(b'$$hint', str(hint).encode())
		)

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

	def read_body_stream(self, no_length_ok:bool=True, autoreject:bool=True, chunksize:int=None):
		"""
		(Generator)
		Progressively read body of the incoming request
		"""

		# important todo: It's speculated that a request can be without content-length
		# important todo: chunked encoding support
		content_length = self.headers.get('content-length')

		if not content_length and not no_length_ok:
			if autoreject:
				self.request.reject(411)
			raise MissingContentLength('The client did not provide mandatory Content-Length header')

		content_length = int(content_length)
		read_progress = 0

		chunksize = chunksize or self.srv_res.cfg['buffers']['stream_receive']

		with DynamicGroupedText('Read Body Stream') as log_group:
			log_group.print('Content Length:', content_length)
			while True:
				if content_length and read_progress >= content_length:
					break
				log_group.print('Waiting for data...')
				received_data = self.cl_con.recv(4096)
				log_group.print('Got data:', len(received_data))
				if not received_data:
					break
				yield received_data
				read_progress += len(received_data)

	# def read_body(self, as_buf=False, maxsize=-1):
	def read_body(self, as_buf=False, maxsize=None, no_length_ok:bool=True, autoreject:bool=True, chunksize:int=None):
		"""
		Read the entire request body in one go.
		"""
		buf = self.srv_res.pylib.io.BytesIO()
		for chunk in self.read_body_stream(no_length_ok, autoreject, chunksize):
			buf.write(chunk)
			if maxsize and buf.tell() > maxsize:
				self.reject(413)
				raise PayloadTooLarge(f'The received payload ({buf.tell()}) exceeds the limit ({maxsize})')
		if as_buf:
			buf.seek(0, 0)
			return buf
		else:
			return buf.getvalue()


	# Processed headers
	# =================

	# A client may ask for an access to a specific chunk of the target file.
	# In this case a "Range" header is present.
	# It has a format of start-end (both inclusive)
	# This function returns an evaluated tuple from the following header.
	# If "Range" header is not present - None is returned.
	# Tuple format is as follows: (int|None, int|None)
	# Negative numbers are clamped to 0
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
		timing_api = server_timings()

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
			evaluated_request = cl_request(cl_con, cl_addr, srv_res, timing_api)
			response = evaluated_request.response

		conlog('Initialized basic room, evaluated request')

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

		# Now either pass the control to the room specified in the config
		# or the default room
		if not evaluated_request.terminated:
			route_info.func(
				evaluated_request,
				evaluated_request.response,
				evaluated_request.response.offered_services
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
			lrec = logRecord(1, request_log | upd_rec_data)
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
			err_rec = logRecord(2, traceback_to_text(err))
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

