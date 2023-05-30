from jag_util import dict_pretty_print

_room_echo = '[Request Evaluator]'

_rebind = print

def print(*args):
	_rebind(_room_echo, *args)



def request_default_action(req):
	print('Executing default action', req.path)

	# fisrt of all check if path explicitly points to a file
	if req.path.is_file():
		# then, check if it's actually inside the docroot
		if not req.path.resolve().is_relative_to(req.server['doc_root']):
			req.reject()
			return

		# all good - set content type send the shit
		req.response.content_type = (
			req.server['cache']['mimes']['base_mimes_signed'][req.path.suffix]
			or
			'application/octet-stream'
		)
		req.response.flush(req.path.read_bytes())
		return


	# if it's not a file - check whether the target dir has an .html file
	if (req.path / 'index.html').is_file():
		req.response.content_type = 'text/html'
		req.response.flush((req.path / 'index.html').read_bytes())
		return

	# othrwise - reject
	req.reject()



class response:
	def __init__(self, req, con, server):
		self.request = req
		self.con = con
		self.server = server
		self.headers = {
			'Server': 'Jag',
		}

		self.content_type = 'application/octet-stream'
		self.code = 200

	# dump headers and response code to the client
	def send_preflight(self):
		"""
		Dump headers to the client
		"""
		import io
		buf = io.BytesIO()

		# response code
		buf.write(f"""HTTP/1.1 {self.server['cache']['response_codes'][self.code]}\r\n""".encode())

		# important todo: better way of achieving this
		self.headers['Content-Type'] = self.content_type

		# headers
		for header_name, header_value in self.headers.items():
			buf.write(f"""{header_name}: {header_value}\r\n""".encode())

		# end
		buf.write('\r\n'.encode())

		# send to the client
		self.con.sendall(buf.getvalue())

		# important todo: There's a built-in way to make function fire only once
		self.send_preflight = lambda: None


	# mark response as a download
	def mark_as_xfiles(self, filename):
		"""
		This is needed if you want the response body to be treated
		as a file download
		"""
		self.headers['Content-Disposition'] = f'attachment; filename="{str(filename)}"'


	# send complete response and close the connection, obviously
	def flush(self, data):
		if not isinstance(data, bytes):
			data = data.getvalue()

		# important todo: the response should either be chunked or have Content-Length header
		self.headers['Content-Length'] = len(data)

		# send headers
		self.send_preflight()

		# send the body
		self.con.sendall(data)

		# terminate
		self.request.terminate()





class incoming_request:
	def __init__(self, con, address, server):
		import time, hashlib, json, io, sys, traceback

		self.con = con
		self.client_addr = address
		self.server = server
		self.info = {}
		self.headers = {}

		self.response = response(self, con, server)

		print('Initialized basic room')

		self._eval_request()


	def _eval_request(self):
		import time, hashlib, json, io, sys, traceback
		from pathlib import Path

		# todo: move this to a shared place
		_hshake_end = (b'\r\n\r\n', b'\n\n')
		_hshake_buf_maxsize = 65535

		# 
		# Any http connection starts with client sending their info (request)
		# 
		request_info = io.BytesIO()
		while True:
			# if last 4 bytes are \r\n\r\n or \n\n - we got the handshake info
			request_info.seek(-4, 2)
			# (reading 4 bytes moves the carret 4 bytes forward, to where it was before, aka end)
			if request_info.read(4) in _hshake_end:
				print('Got request buffer, proceed')
				break
			# discard handshakes that are too large
			if request_info.tell() > _hshake_buf_maxsize:
				self.con.close()
				sys.exit()
				print('Request too large, closing connection')
				return
			# otherwise - keep populating buffer
			hshake_data = self.con.recv(4096)
			# print(hshake_data)
			request_info.write(hshake_data)

		request_info = request_info.getvalue()

		print(request_info.decode())

		request_info = request_info.decode().split('\r\n')

		print('\n'.join(request_info))

		# 
		# Evaluate the request
		# 

		# First line is always the request protocol, path and http version
		# It's up to the client to send valid data
		self.type, self.path, self.protocol = request_info[0].split(' ')
		print(self.type, self.path, self.protocol)

		# evaluate path
		self.path = self.server['doc_root'] / Path(self.path.lstrip('/'))

		# Delete the first line as it's not needed anymore
		del request_info[0]

		# parse the remaining into a dict
		request_dict = {}
		for line in request_info:
			# skip empty stuff
			if line.strip() == '':
				continue
			line_split = line.split(': ')
			request_dict[line_split[0].lower()] = ': '.join(line_split[1:])

		dict_pretty_print(request_dict)

		#
		# Now evaluate stuff one by one
		#
		_nm = 'pragma'
		if _nm in request_dict:
			self.info[_nm] = request_dict[_nm]
			del request_dict[_nm]

		_nm = 'cache-control'
		if _nm in request_dict:
			self.info[_nm] = request_dict[_nm]
			del request_dict[_nm]

		_nm = 'user-agent'
		if _nm in request_dict:
			self.info[_nm] = request_dict[_nm]
			del request_dict[_nm]

		_nm = 'accept'
		if _nm in request_dict:
			self.info[_nm] = request_dict[_nm].split(',')
			del request_dict[_nm]

		_nm = 'accept-encoding'
		if _nm in request_dict:
			self.info[_nm] = request_dict[_nm].split(',')
			del request_dict[_nm]

		_nm = 'cookie'
		if _nm in request_dict:
			cookie_dict = {}
			cookie_pairs = request_dict[_nm].split('; ')
			for cpair in cookie_pairs:
				cpair_split = cpair.split('=')
				cookie_dict[cpair_split[0]] = '='.join(cpair_split[1:])

			self.info['cookies'] = cookie_dict
			del request_dict[_nm]

		# Dump the rest into a dict
		self.headers = request_dict

		if 'cookie' in request_dict:
			dict_pretty_print(cookie_dict)
		print('')
		dict_pretty_print(self.info)


	def exec_default_action(self):
		request_default_action(self)


	def terminate(self):
		import socket
		self.con.shutdown(socket.SHUT_RDWR)
		self.con.close()


	def reject(self, code=401):
		self.response.code = code
		self.response.content_type = 'text/html'
		self.response.flush(
			self.server['cache']['assets']['html']['default_reject']
			.replace(b'$$reason', self.server['cache']['response_codes'][code].encode())
		)



def base_room(con, address, server):
	import time, hashlib, json, io, sys, traceback
	"""
	Basic room for handling incoming requests.
	Serves basic purpose like responding with images and html pages.
	"""
	try:
		sex = incoming_request(con, address, server)
		sex.exec_default_action()
		con.close()
		sys.exit()
	except Exception as e:
		print( "EXCEPTION TRACE PRINT:\n{}".format( "".join(traceback.format_exception(type(e), e, e.__traceback__))))
		raise e


