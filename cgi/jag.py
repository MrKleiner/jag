

class jag_server:
	def __init__(self):
		import cgi, sys, cgitb
		import os, json, platform
		from pathlib import Path

		self._fatal_err_msg =         """$JAG_FATAL_ERR_MSG$"""
		self._regular_err_msg =       """$JAG_REGULAR_ERR_MSG$"""
		self._jtw_no_action_reason =  """$JAG_JATEWAY_ACTION_NOT_FOUND_MSG$"""
		self._xfiles_hname =          """$JAG_X_FILES_HNAME$"""
		self._action_url_param_name = """$JAG_ACT_URL_PRM_NAME$"""

		self.response_content_type = 'application/octet-stream'


		# traceback messages
		cgitb.enable(format='text')

		# don't import modules many times...
		self.cgitb = cgitb
		self.Path = Path
		self.json = json
		self.sys = sys
		self.os = os

		self.output = sys.stdout.buffer.write

		# buffer to flush
		self.sv_buffer = b''

		# parse url params into a dict, if any
		get_cgi_params = cgi.parse()
		url_params = {}
		for it in get_cgi_params:
			url_params[it] = ''.join(get_cgi_params[it])
		self.prms = url_params

		# parse http headers into a dict, if any
		self.headers = {}
		for hd in os.environ:
			# print(hd, os.environ[hd], '\n')
			if hd.startswith('HTTP_'):
				self.headers[hd.replace('HTTP_', '').lower()] = os.environ[hd]

		# get cookies
		# important todo: is it really neccessary to postpone cookie evaluation ?
		self._cookies = None
		self._outp_cookies = {}


		# read body content, if any
		self.bin = b''
		# response headers are the ones this script is about to output to the client
		self.response_headers = {}
		# todo: there are definitely better ways of determining whether the body content could be read or not
		try:
			self.bin = sys.stdin.buffer.read()
		except:
			pass

		# todo: just don't bother and distribute two separate versions for linux and for windows ?
		self.platform = platform.system().lower()

		# also make cgitb write errors to files
		# if $JAG_BURN
		# cgitb.enable(format='text', logdir=str(self.sysdb_path / 'cgi_err'))







	def bin_as_json(self):
		return self.json.loads(self.bin)


	@property
	def cookies(self):
		if self._cookies:
			return self._cookies

		for cookie in self.os.environ['HTTP_COOKIE'].split(';'):
			csplit = cookie.split('=')
			self._cookies[csplit[0]] = '='.join(csplit[1:])


	def set_cookie(self, cname, cval):
		self._outp_cookies[cname] = cval


	# @property
	# def tr_type(self):
	# 	return self._tr_type

	# @tr_type.setter
	# def tr_type(self, newname):
		# pass

	# add error header with specified data
	def fatal_error(self, err):
		self.set_header(self._fatal_err_msg, str(err))

	def error(self, err):
		self.set_header(self._regular_err_msg, str(err))


	# spit shit
	# either fill the buffer gradually with .bin_write and then flush
	# or flush bytes immediately by passing bytes to the flush function
	def flush(self, add_b=None):
		if add_b:
			self.bin_write(add_b)
		# add headers
		for h in self.response_headers:
			# try:
			# 	hv = self.response_headers[h].encode()
			# except:
			# 	hv = str(self.response_headers[h]).encode()

			# try:
			# 	h = h.encode()
			# except:
			# 	h = str(h).encode()

			# todo: what if either key/value has \r\n in it ?
			self.output(f'{h}: {self.response_headers[h]}\r\n'.encode())

		# add cookies
		for biscuit in self._outp_cookies:
			self.output(f"""Set-Cookie: {biscuit}={self._outp_cookies[biscuit]}\r\n""".encode())

		# content type
		self.output(f'Content-Type: {self.response_content_type}\r\n\r\n'.encode())
		# buffer
		self.output(self.sv_buffer)
		# do flush
		self.sys.stdout.buffer.flush()
		self.sys.stdout.flush()
		self.sys.exit()


	def flush_json(self, j):
		self.bin_jwrite(j)
		self.flush()


	def set_header(self, hkey, hval):
		self.response_headers[hkey] = hval

	# add to bin
	# expects bytes
	def bin_write(self, dat):
		if not isinstance(dat, bytes):
			raise Exception('Jag: Cant add anything besides bytes to output buffer')

		self.sv_buffer += dat

	# add json to bin
	def bin_jwrite(self, jsn):
		self.sv_buffer += self.json.dumps(jsn).encode()


	# spit file
	def x_files(self, flpath=None, flname=None):

		if not flpath or not flname:
			raise Exception('Jag: x_files transfer: one of the arguments is completely invalid')

		floc = self.Path(flpath)

		if not floc.is_file():
			raise Exception('Jag: x_files transfer: file path does not exist')

		# src from hello.py:
		# sys.stdout.write(b'Content-Type: application/octet-stream\r\n')
		# sys.stdout.write(b'Content-Disposition: attachment; filename="bigfile.mp4"\r\n')
		# sys.stdout.write(b'X-Sendfile: /home/basket/scottish_handshake/db/20181225_182650.ts\r\n\r\n')

		self.output('Content-Type: application/octet-stream\r\n'.encode())
		self.output(f"""Content-Disposition: attachment; filename="{str(flname)}"\r\n""".encode())
		self.output(f"""{self._xfiles_hname}: {str(floc)}\r\n\r\n""".encode())

		self.sys.stdout.buffer.flush()
		self.sys.stdout.flush()
		self.sys.exit()


	# it shouldn't be here, but it's here because of performance reasons
	# loads json from a path
	def jload(self, pth):
		return self.json.loads(self.Path(pth).read_bytes())




class jateway:
	"""
	This gateway allows executing functions through a proxy
	to properly catch errors and report them to the client
	"""
	def __init__(self, srv, registry={}):
		self.reg = registry
		self.srv = srv
		self.action = self.srv.prms.get(self.srv._action_url_param_name)

		self._eval_action()

	def _eval_action(self):
		try:
			# if action from url params is in the registry then execute
			if self.action in self.reg:
				self.reg[self.action]()
			else:
				# todo: is it really a fatal error?
				self.srv.fatal_error('invalid_action')
				self.srv.flush(f"""Details: Requested: {self.action}, Available: {self.reg}""".encode())
		except Exception as e:
			# The way this works is pretty interesting:

			# When exception occurs upon module action evaluation - 
			# the server outputs a header to the output buffer which indicates that a fatal error occured
			# and then raises the error

			# When an error is raised, the cgitb module adds a PROPERLY FORMATTED error traceback to the output buffer
			# IN ADDITION to the header indicating that a fatal error occured
			# Not only that, but cgitb also dumps the error to the logs folder

			# The most important part is that all of the above happens
			# while keeping the client aware of the said fatal error

			# todo: cgitb simply binds a handler to exceptions. Do it manually without cgitb ?

			self.srv.output(f'{self.srv._fatal_err_msg}: {self.srv._jtw_no_action_reason}\r\n'.encode())
			# todo: citb adds appropriate content type automatically
			self.srv.output('Content-Type: application/octet-stream\r\n\r\n'.encode())

			raise e


	def eval_action(self):
		return True




