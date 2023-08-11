from jag_util import dict_pretty_print, print_exception, traceback_to_text, conlog

# from pathlib import Path
# import sys
# sys.path.append(str(Path(__file__).parent))

from jag_logging import logRecord

_room_echo = '[Request Evaluator]'

_rebind = print


def echo_exception_to_client(err, con):
	import traceback

	try:
		trback = ''.join(
			traceback.format_exception(
				type(err),
				err,
				err.__traceback__
			)
		)
	except Exception as e:
		trback = f'Jag critical error: {err}'

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
		self.headers = {
			'Server': 'Jag',
			# 'Server-Timings': '',
		}
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
		for header_name, header_value in self.headers.items():
			self.cl_con.sendall(
				f"""{header_name}: {header_value}\r\n""".encode()
			)

		# send cookies, if any
		# important todo: this is very slow
		if self.add_cookies:
			cbuf = self.srv_res.pylib.io.BytesIO()
			for cookie in self.add_cookies:
				cbuf.write(b'Set-Cookie: ')
				cbuf.write(cookie)
				cbuf.write(b'\r\n')
			self.cl_con.sendall(cbuf.getvalue())

		# Send an extra \r\n to indicate the end of headers
		self.cl_con.sendall('\r\n'.encode())

		# important todo: There's a built-in way to make functions only fire once
		# Yes, BUT, it costs A LOT of time and effort for the machine
		# Such a simple buttplug is WAY more efficient
		self.send_preflight = lambda: None

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


	def set_cookie(self, cname, cval, domain=None, expires=None, secure=False, path=None, httponly=False, max_age=None, samesite=None):
		"""
		Adds one Set-Cookie header per call.
		"expires" parameter accepts datetime objects.
		"""
		datetime = self.srv_res.pylib.datetime
		# This is retarded...
		wday_picker = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
		month_picker = [
			'_',
			'Jan',
			'Feb',
			'Mar',
			'Apr',
			'May',
			'Jun',
			'Jul',
			'Aug',
			'Sep',
			'Oct',
			'Nov',
			'Dec',
		]

		cookie_buf = self.srv_res.pylib.io.BytesIO()
		cookie_buf.write(f'{cname}={cval}'.encode())

		if domain:
			cookie_buf.write(f'; Domain={domain}'.encode())
		if expires:
			formatted_expires = expires
			if isinstance(expires, datetime.datetime):
				asutc = expires.astimezone(datetime.timezone.utc)
				formatted_expires = f"""{wday_picker[asutc.weekday()]}, {asutc.day} {month_picker[asutc.month]} {asutc.year} {asutc.strftime('%H:%M:%S')} GMT"""
			cookie_buf.write(f'; Expires={formatted_expires}'.encode())
		if secure == True:
			cookie_buf.write(b'; Secure')
		if path:
			cookie_buf.write(f'; Path={path}'.encode())
		if httponly:
			cookie_buf.write(b'; HttpOnly')
		if max_age:
			cookie_buf.write(f'; Max-Age={max_age}'.encode())
		if samesite:
			cookie_buf.write(f'; SameSite={samesite.capitalize()}'.encode())

		self.add_cookies.append(cookie_buf.getvalue())




class cl_request:
	def __init__(self, cl_con, cl_addr, srv_res, timing_api):
		self.cl_con = cl_con
		self.cl_addr = cl_addr
		self.srv_res = srv_res
		self.timings = timing_api

		self.headers = {}

		# Initialize the response class
		# Early init of this class is needed
		# for rejecting certain requests
		with self.timings.record('rsp_class_init', _internal=True):
			self.response = sv_response(self, cl_con, srv_res)

		# Some widely-used headers are lazily processed
		# for easier use
		self._cookie = None
		self._cache_control = None
		self._accept = None
		self._byterange = None

		# Try/Except in case of malformed request
		# Why bother?
		# It's client's responsibility to perform good requests
		try:
			self.eval_request()
		except Exception as e:
			self.reject(400)
			raise e
		

	# Init
	# =================

	# Obsolete
	def _collect_head_buf(self):

		io = self.srv_res.pylib.io

		self.head_buf = io.BytesIO()
		self.body_buf = io.BytesIO()

		double_rn = 0
		expect_r = False

		# important todo: This is extremely (relatively) slow
		# simple http server from python base library does something like
		# do 1 byte receive from client till \r\n\r\n
		# OR
		# Read 65535 bytes and then process the thing
		while True:
			data = self.cl_con.recv(65535)
			for idx, char in enumerate(data):
				# conlog('Char:', chr(char).encode())

				if char != 10 and char != 13:
					# conlog('^ no match, abort')
					expect_r = False
					double_rn = 0
					continue

				if char == 13:
					# conlog('^ found 13')
					expect_r = True
					continue

				if expect_r and char != 10:
					# conlog('^ is not 10, abort')
					expect_r = False
					double_rn = 0
					continue

				if expect_r and char == 10:
					# conlog('^ found 10, +1')
					double_rn += 1
					expect_r = False

				if double_rn == 2:
					# conlog('Writing to body buffer:', bytes(data[(idx+1):]))
					self.body_buf.write(bytes(data[(idx+1):]))
					self.head_buf.write(bytes(data[:idx]))
					break

			if double_rn == 2:
				conlog('Header Buf', self.head_buf.getvalue().decode())
				break

			self.head_buf.write(data)

			if self.head_buf.tell() >= self.srv_res.cfg['buffers']['max_header_len']:
				self.response.reject(431)
				break


	# Keep eating bytes from the client
	# until the entire Request Header arrives
	def collect_head_buf(self):
		read_limit = self.srv_res.cfg['buffers']['max_header_len']
		# bufsize = 0
		self.header_fields = []

		rfile = self.cl_con.makefile('rb', newline=b'\r\n')
		conlog('created virtual file')
		while True:
			if read_limit <= 0:
				self.reject(431)
				break
			line = rfile.readline(read_limit)
			conlog('read line', line)

			# it's important to also count \r\n\t etc.
			read_limit -= len(line)

			# encountered end of the header fields
			if line == b'\r\n':
				conlog('Encountered fields end', line)
				break

			# append field to the buffer
			self.header_fields.append(line.decode().strip())


	# Request evaluation has a dedicated function for easier error handling
	def eval_request(self):
		# io = self.srv_res.pylib.io
		# sys = self.srv_res.pylib.sys
		urllib = self.srv_res.pylib.urllib
		Path = self.srv_res.pylib.Path

		# Fully custom method of receiving the Request Header
		# gives a lot of benefits (as well as causing mental retardation)
		with self.timings.record('collect_hbuf', _internal=True):
			self.collect_head_buf()


		with self.timings.record('eval_hbuf', _internal=True):
			# raw bytes of the header
			# header_data = self.head_buf.getvalue()
			# conlog(header_data.decode())

			# split header into lines
			# header_data = header_data.decode().split('\r\n')
			header_fields = self.header_fields
			conlog('\n'.join(header_fields))

			# First line of the header is always [>request method< >path< >http version<]
			# It's up to the client to send valid data
			self.method, self.path, self.protocol = header_fields[0].split(' ')
			conlog(self.method, self.path, self.protocol)
			self.method = self.method.lower()

			# deconstruct the url into components
			parsed_url = urllib.parse.urlparse(self.path)

			# important todo: lazy processing
			# first - evaluate query params
			self.query_params = {k:(''.join(v)) for (k,v) in urllib.parse.parse_qs(parsed_url.query, True).items()}
			conlog('Url params:', self.query_params)

			# then, evaluate path
			decoded_url_path = urllib.parse.unquote(parsed_url.path)
			self.abspath = self.srv_res.doc_root / Path(decoded_url_path.lstrip('/'))
			self.relpath = Path(decoded_url_path.lstrip('/'))
			self.trimpath = decoded_url_path

			# Delete the first line as it's no longer needed
			del header_fields[0]

			# parse the remaining headers into a dict
			request_dict = {}
			for line in header_fields:
				# skip empty stuff
				if line.strip() == '':
					continue
				line_split = line.split(': ')
				request_dict[line_split[0].lower()] = ': '.join(line_split[1:])

			dict_pretty_print(request_dict)

			self.headers = request_dict


		# make sure this function doesn't trigger twice
		self.eval_request = lambda: None


	# Actions
	# =================

	# Properly collapse the tunnel between server and client
	def terminate(self):
		socket = self.srv_res.pylib.socket
		self.cl_con.shutdown(socket.SHUT_RDWR)
		self.cl_con.close()

		# Termination is only possible once
		self.terminate = lambda: None

	# Send a very simple html document
	# with a short description of the provided Status Code
	def reject(self, code=401, hint=''):
		self.response.code = code
		self.response.content_type = 'text/html'
		self.response.flush_buffer(
			self.srv_res.reject_precache
			.replace(b'$$reason', self.srv_res.response_codes.get(code, f'{code} ERROR').encode())
			.replace(b'$$hint', str(hint).encode())
		)

	def redirect(self, target, reason=7, softlink=False):
		"""
		Redirect the request to the target destination.
		- target: target URL to redirect to
		- reason: 0-8 (300, 301, 302...), default to 7 (307)
		- softlink: False = Location. True = Content-Location
		"""
		# self.srv_res.response_codes.get
		reason_picker = {code:(300+code) for code in range(7)}
		self.response.code = reason_picker.get(reason, 307)
		self.response.headers['Content-Location' if hardlink else 'Location'] = str(target)

		self.response.send_preflight()
		self.terminate()

	# I cannot be bothered. Here, have *args and fuckoff
	def match_path(self, action_dict, *args, trim_path=True):
		"""
		Sample set/list:
		{
			('/pootis/sandwich/dispenser', func_name1),
			('/pootis',                    func_name2),
		}
		"""
		comparator = '/' + self.relpath.as_posix()

		for rpath, func in action_dict:
			if comparator.startswith(rpath):
				if trim_path:
					self.trimpath = self.srv_res.pylib.Path(comparator.lstrip(rpath))
				return func(self, self.response, self.response.offered_services, *args)

		# if no match was found - return false
		# todo: return some sort of a variable/class,
		# so that it's more specific
		return False


	def read_body_stream(self):
		"""
		(Generator)
		Progressively read body of the incoming request
		"""
		content_length = int(self.headers['content-length'])
		read_progress = self.body_buf.seek(0, 2)
		yield self.body_buf.getvalue()
		while True:
			if read_progress >= content_length:
				break
			# todo: finetune this value
			# or expose it in the config
			received_data = self.cl_con.recv(65535)
			yield received_data
			read_progress += len(received_data)


	def read_body(self, as_buf=False):
		import io
		buf = io.BytesIO()
		for chunk in self.read_body_stream():
			buf.write(chunk)

		if as_buf:
			buf.seek(0, 0)
			return buf
		else:
			return buf.getvalue()


	# Utility
	# =================
	def parse_kv(self, kvs, separator=',', key_to_lower=True):
		pairs = kvs.split(separator)
		result = {}
		for pair in pairs:
			pair_split = pair.split('=')
			if key_to_lower:
				pair_split[0] = pair_split[0].upper()

			if len(pair_split) == 1:
				result[pair_split[0]] = True
				continue

			val = '='.join(pair_split[1:])
			# important todo: is this really needed ?
			try:
				val = float(val)
			# important todo: generic exceptions are very bad
			except:
				pass
			try:
				val = int(val)
			except:
				pass

			result[pair_split[0]] = val

		return result


	# Processed headers
	# =================

	@property
	def cookie(self):
		"""
		Nicely formatted cookie header
		"""
		if self._cookie:
			return self._cookie

		cookie_data = self.headers.get('cookie')
		if not cookie_data:
			return None

		self._cookie = self.parse_kv(cookie_data, separator=';')

		return self._cookie

	# Even though server doesn't support advanced caching...
	@property
	def cache_control(self):
		if self._cache_control:
			return self._cache_control

		cache_data = self.headers.get('cache-control')
		if not cache_data:
			return None

		self._cache_control = self.parse_kv(cookie_data, separator=',')

		return self._cache_control


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
def base_room(cl_con, cl_addr, srv_res):
	import time
	import importlib.util
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

		# precache some commonly-used python libraries
		# important todo: is this even needed?
		with timing_api.record('lib_cache', _internal=True):
			srv_res.reload_libs()

		request_log = {
			'time': srv_res.pylib.datetime.datetime.now(),
		}

		# Evaluate the request
		with timing_api.record('rq_eval', _internal=True):
			evaluated_request = cl_request(cl_con, cl_addr, srv_res, timing_api)

		conlog('Initialized basic room, evaluated request')



		# ----------------
		# Execute action
		# ----------------

		# Now either pass the control to the room specified in the config
		# or the default room
		if srv_res.cfg['room_file']:
			with timing_api.record('spec', _internal=True):
				spec = importlib.util.spec_from_file_location('main', str(srv_res.cfg['room_file']))
				custom_func = importlib.util.module_from_spec(spec)
				spec.loader.exec_module(custom_func)

			custom_func.main(
				evaluated_request,
				evaluated_request.response,
				evaluated_request.response.offered_services
			)
		else:
			_default_room(
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
				'usragent': ev_rq.headers.get('user-agent'),
				'ref': ev_rq.headers.get('referer'),
				'rsp_code': ev_rq.response.code,
			}

			# create log record class
			lrec = logRecord(1, request_log | upd_rec_data)
			# send record to the logging server
			lrec.push()


	except ConnectionAbortedError as err:
		conlog('Connection was aborted by the client')
	except ConnectionResetError as err:
		cpnlog('Connection was reset by the client')
	except Exception as err:
		import traceback
		conlog(
			''.join(
				traceback.format_exception(
					type(err),
					err,
					err.__traceback__
				)
			)
		)

		echo_exception_to_client(err, cl_con)

		err_rec = logRecord(2, traceback_to_text(err))
		err_rec.push()

		raise err


	import sys
	# conlog('        Exiting...', evaluated_request.cl_addr[1])

	# cl_con.shutdown(2)
	cl_con.close()
	sys.exit()



