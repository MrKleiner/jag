
_room_echo = '[Request Evaluator]'

_rebind = print

def print(*args):
	_rebind(_room_echo, *args)

def dict_pretty_print(d):
	sex = '\n'
	for key in d:
		sex += f"""{('>' + str(key) + '<').ljust(30)} :: >{str(d[key])}<""" + '\n'

	print(sex)


class incoming_request:
	def __init__(self, con, address, server_cache=None):
		import time, hashlib, json, io, sys, traceback

		self.con = con
		self.client_addr = address
		self.server_cache = server_cache
		self.info = {}
		self.headers = {}
		print('Initialized basic room')

		try:
			self._eval_request()
		except Exception as e:
			print( "EXCEPTION TRACE PRINT:\n{}".format( "".join(traceback.format_exception(type(e), e, e.__traceback__))))
			raise e


	def _eval_request(self):
		import time, hashlib, json, io, sys, traceback

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

		# GET /sex/po%20otis/sandwich.jpeg HTTP/1.1
		# -Host: 192.168.0.10:56817
		# Connection: keep-alive
		# Pragma: no-cache
		# Cache-Control: no-cache
		# Upgrade-Insecure-Requests: 1
		# User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36
		# Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7
		# Accept-Encoding: gzip, deflate
		# Accept-Language: en-US,en;q=0.9
		# Cookie: sex=ded; aaa=bbb !CAN BE ABSENT

		# First line is always the request protocol, path and http version
		# It's up to the client to send valid data
		self.type, self.path, self.protocol = request_info[0].split(' ')
		print(self.type, self.path, self.protocol)

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

		dict_pretty_print(cookie_dict)
		print('')
		dict_pretty_print(self.info)


	def _test(self):
		from pathlib import Path

		pootis = Path(r"E:\!webdesign\jag\test\bottom_gear.png")

		rsp = b''

		rsp += b'HTTP/1.1 200 OK' + b'\r\n'
		# rsp += b'Transfer-Encoding: chunked' + b'\r\n'
		rsp += b'Content-Type: ' + self.server_cache['mimes']['base_mimes_signed'][pootis.suffix].encode() + b'\r\n'

		nen = pootis.read_bytes()

		rsp += b'Content-Length: ' + str(len(nen)).encode() + b'\r\n\r\n'

		rsp += nen

		self.con.sendall(rsp)





def base_room(con, address, server_cache=None):
	import time, hashlib, json, io, sys, traceback
	"""
	Basic room for handling incoming requests.
	Serves basic purpose like responding with images and html pages.
	"""
	try:
		sex = incoming_request(con, address, server_cache)
		sex._test()
		con.close()
		sys.exit()
	except Exception as e:
		print( "EXCEPTION TRACE PRINT:\n{}".format( "".join(traceback.format_exception(type(e), e, e.__traceback__))))
		raise e


