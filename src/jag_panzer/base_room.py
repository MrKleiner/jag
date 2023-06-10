from jag_util import dict_pretty_print


_room_echo = '[Request Evaluator]'
_rebind = print

def conlog(*args):
	print(_room_echo, *args)



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
	request.reject()



# A bunch of default services the server can provide
class sv_services:
	"""
	A bunch of default services the server can provide.
	Most notable one: Serving GET requests
	"""
	def __init__(self, request, response):
		self.request = request
		self.response = response

	# Serve a file to the client in a CDN manner
	# If no file is provided - serve path from the request
	def serve_file(self, tgt_file=None, respect_range=True):
		"""
		Serve a file to the client.
		It's possible to specify a target file.
		If no target file is specified, then reuqest path is used.
		- tgt_file: Path to the file to serve, defaults to request path.
		- respect_range: Take the "Range" header into account.
		"""
		request = self.request
		response = self.response

		if not request.abspath.is_file():
			self.request.reject()
			return

		# all good - set content type and send the shit
		response.content_type = (
			request.srv_res.mimes['signed'].get(request.abspath.suffix)
			or
			'application/octet-stream'
		)

		# if the size is too big for a single flush - stream in chunks
		# This is very important, because serving a 2kb svg in chunks slows the response time
		# and serving an 18gb .mkv Blu-ray remux in a single flush is impossible
		if request.abspath.stat().st_size > request.srv_res.cfg['buffers']['max_file_len']:
			with open(str(request.abspath), 'r+b') as f:
				# if request comes with a Range header - try serving the requested byterange
				# '0-' VERY funny, fuck right off
				if request.byterange and (request.headers.get('range', 'bytes=0-').strip() != 'bytes=0-') and respect_range:
					conlog('The client has fucked us over:', request.headers.get('range', '0-').strip())
					response.serve_range(f)
				else:
					response.stream_buffer(f, (1024*1024)*5)
		else:
			response.flush_buffer(request.abspath.read_bytes())

		self.request.terminate()

	# List directory as an html page
	def list_dir(self):
		"""
		- Set content type to text/html
		- Progressively generate listing for a directory and stream it to the client
		- Close connection
		"""
		self.response.content_type = 'text/html'

		with self.response.stream_bytechunks() as stream:
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
	def __init__(self, request, cl_con, self_terminate):
		self.cl_con = cl_con
		self.request = request
		self.auto_term = self_terminate

	def __enter__(self):
		return self

	def __exit__(self, type, value, traceback):
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

# RANGES ARE INCLUSIVE IN HTTP !
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
		self.headers = {
			'Server': 'Jag',
		}

		self.content_type = 'application/octet-stream'
		self.code = 200

		self.offered_services = sv_services(self.request, self)

	# dump headers and response code to the client
	def send_preflight(self):
		"""
		Dump headers and response code to the client
		"""

		# send response code
		self.cl_con.sendall(
			f"""HTTP/1.1 {self.srv_res.response_codes[self.code]}\r\n""".encode()
		)

		# important todo: better way of achieving this
		self.headers['Content-Type'] = self.content_type

		# send headers
		for header_name, header_value in self.headers.items():
			self.cl_con.sendall(
				f"""{header_name}: {header_value}\r\n""".encode()
			)

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

	def stream_bytechunks(self, self_terminate=True):
		"""
		Stream data to the client in HTTP chunks:
		- set 'Transfer-Encoding' header to 'chunked'
		- Dump headers
		- Start streaming chunks:
			- This returns an object for use with "with" keyword.
			- The object only has 1 method: send()
			  Which only takes 1 argument: Bytes to send
		"""

		# This cannot be otherwise
		self.headers['Transfer-Encoding'] = 'chunked'
		# It's impossible to stream multiple groups of chunks
		self.send_preflight()

		return _chunkstream(self.request, self.cl_con, self_terminate)

	# Automated action:
	# - Add 'Transfer-Encoding: chunked' header
	# - Send headers to the client
	# - Stream the entirety of the provided buffer in chunks
	# - Collapse the connection
	def stream_buffer(self, data, chunk_size=None):
		"""
		Send the data in chunks.
		data = io.BytesIO object.
		chunk_size = the size of a single chunk in bytes, default to server config
		Example usage: Pass buffer of an open file to stream it to the client.
		"""

		# The response is EITHER chunked OR has Content-Length
		self.headers['Transfer-Encoding'] = 'chunked'

		# first - dump headers
		self.send_preflight()

		# Safety (tin foil hat): Move the carret to the very beginning of the buffer
		data.seek(0, 0)
		# stream chunks
		with self.stream_bytechunks() as stream:
			while True:
				# read chunk
				chunk = data.read(
					chunk_size or self.srv_res.cfg['buffers']['bufstream_chunk_len']
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
		with self.stream_bytechunks() as stream:
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






class cl_request:
	def __init__(self, cl_con, cl_addr, srv_res):
		self.cl_con = cl_con
		self.cl_addr = cl_addr
		self.srv_res = srv_res

		self.headers = {}

		# Initialize the response class
		# Early init of this class is needed
		# for rejecting certain requests
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
			self._eval_request()
		except Exception as e:
			self.reject(400)
			raise e
		

	# Init
	# =================

	# Keep eating bytes from the client
	# until the entire Request Header arrives
	def collect_head_buf(self):

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

	# Request evaluation has a dedicated function for easier error handling
	def _eval_request(self):
		# io = self.srv_res.pylib.io
		# sys = self.srv_res.pylib.sys
		urllib = self.srv_res.pylib.urllib
		Path = self.srv_res.pylib.Path

		# Fully custom method of receiving the Request Header
		# gives a lot of benefits
		self.collect_head_buf()

		# raw bytes of the header
		header_data = self.head_buf.getvalue()
		conlog(header_data.decode())

		# split header into lines
		header_data = header_data.decode().split('\r\n')
		conlog('\n'.join(header_data))

		# First line of the header is always the request method, path and http version
		# It's up to the client to send valid data
		self.method, self.path, self.protocol = header_data[0].split(' ')
		conlog(self.method, self.path, self.protocol)
		self.method = self.method.lower()

		# deconstruct the url into components
		parsed_url = urllib.parse.urlparse(self.path)

		# important todo: lazy processing
		# first - evaluate query params
		self.query_params = {k:(''.join(v)) for (k,v) in urllib.parse.parse_qs(parsed_url.query, True).items()}

		# then, evaluate path
		decoded_url_path = urllib.parse.unquote(parsed_url.path)
		self.abspath = self.srv_res.doc_root / Path(decoded_url_path.lstrip('/'))
		self.relpath = Path(decoded_url_path.lstrip('/'))
		self.trimpath = self.relpath

		# Delete the first line as it's no longer needed
		del header_data[0]

		# parse the remaining headers into a dict
		request_dict = {}
		for line in header_data:
			# skip empty stuff
			if line.strip() == '':
				continue
			line_split = line.split(': ')
			request_dict[line_split[0].lower()] = ': '.join(line_split[1:])

		dict_pretty_print(request_dict)

		self.headers = request_dict


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
			.replace(b'$$reason', self.srv_res.response_codes[code].encode())
			.replace(b'$$hint', str(hint).encode())
		)

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
			# print(rpath, 'startswith', )
			if comparator.startswith(rpath):
				if trim_path:
					self.trimpath = self.srv_res.pylib.Path(comparator.lstrip(rpath))
				return func(self, self.response, self.response.offered_services, *args)

		# if no match was found - return false
		return False


	def read_body_stream(self):
		"""
		(Generator)
		Progressively read the incoming body of the request
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
def base_room(cl_con, cl_addr, srv_res):
	import sys, traceback
	import importlib.util

	try:
		# precache some commonly-used python libraries
		# important todo: is this even needed?
		srv_res.reload_libs()

		# Evaluate the request
		evaluated_request = cl_request(cl_con, cl_addr, srv_res)
		conlog('Initialized basic room, evaluated request')

		# Create service object
		# offered_services = sv_services(evaluated_request, evaluated_request.response)

		# Now either pass the control to the room specified in the config
		# or the default room
		if srv_res.cfg['room_file']:
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

	except Exception as err:
		conlog(
			''.join(
				traceback.format_exception(
					type(err),
					err,
					err.__traceback__
				)
			)
		)

		_trback = ''.join(
			traceback.format_exception(
				type(err),
				err,
				err.__traceback__
			)
		)
		cl_con.sendall('HTTP/1.1 500 Internal Server Error\r\n'.encode())
		_rcontent = f"""<!DOCTYPE HTML>
			<html>
				<head>
					<meta http-equiv="Content-Type" content="text/html;charset=utf-8">
					<title>Rejected</title>
				</head>
				<body>
					<h1>500 Internal Server Error</h1>
					<h3>Server: Jag</h3>
					<p style="white-space: pre;">{_trback}</p>
				</body>
			</html>
		"""
		cl_con.sendall(f'Content-Length: {len(_rcontent)}\r\n\r\n'.encode())
		cl_con.sendall(_rcontent.encode())

		raise err


	cl_con.close()
	sys.exit()



