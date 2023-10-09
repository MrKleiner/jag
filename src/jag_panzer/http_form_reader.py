
class MultipartFormFieldStreamReader:
	def __init__(self, cl_con:socket.socket, f_reader:'MultipartFormReader'):
		self.cl_con = cl_con
		self.f_reader = f_reader
		self.done = False

		self.boundary_len = len(self.f_reader.boundary)

		self.skt_file = self.cl_con.makefile('rb', buffering=0)

		self.boundary_detector = ByteSequenceStopper(self.f_reader.boundary)
		self.end_boundary_detector = ByteSequenceStopper(self.f_reader.boundary + b'--')

	def __enter__(self):
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		self.skt_file.close()
		self.boundary_detector.close()
		self.end_boundary_detector.close()

	def read(self, amount:int=4096) -> bytes:
		buf = io.BytesIO()
		while True:
			data = self.skt_file.read(self.f_reader.boundary_len)
			if not data:
				raise StopExecution(
					'The client has aborted the connection'
				)

			cont_bound = self.boundary_detector.feed(data)
			end_bound = self.end_boundary_detector.feed(data)

			buf.write(data)


class MultipartFormField:
	def __init__(
		self,
		request:'ClientRequest',
		response:ServerResponse,
		f_reader:'MultipartFormReader',
		hfields:HeaderFields,
		autoreject:bool
	):
		self.request = request
		self.response = response
		self.f_reader = f_reader
		self.cl_con = request.cl_con
		self.autoreject = autoreject

		hfields.collect()
		self.headers = jag_http_ents.HTTPHeaders(hfields.lines)

		self.disposition = jag_http_ents.HTTPHeaderKV(
			self.headers['content-disposition'], delimeter='; '
		)
		self.content_type = self.headers['content-type']
		self.name = self.disposition['name']
		self.filename = self.disposition['filename']

		self.finished = False

	def read_body_stream(self) -> MultipartFormFieldStreamReader:
		"""\
		Read field from body as a stream.
		Aka the form has a 10GB file attached.
		"""
		return MultipartFormFieldStreamReader(self.cl_con)

	def read_body_whole(
		self,
		maxsize:int=65535,
		as_buf:bool=False,
		autoreject:bool=None
	) -> bytes|io.BytesIO:
		"""\
		Read the entire field body at once.
		Aka the form has a small text file attached.
		Maxsize is mandatory, because otherwise this is pointless:
		Troll requests may send petabytes of data.
		Maxsize default to 65kb
		"""

		buf = io.BytesIO()
		with self.read_body_stream() as stream:
			while True:
				data = stream.read()
				if not data:
					break
				buf.write(data)

				if buf.tell() > maxsize:
					break

		if buf.tell() > maxsize:
			msg = f'Field {self.name} is too large'
			autoreject = autoreject if autoreject is not None else self.autoreject

			if autoreject:
				self.request.reject(413, msg)
				raise StopExecution(msg)
			else:
				raise PayloadTooLarge(msg)

		if as_buf:
			return buf
		else:
			return buf.getvalue()


class MultipartFormReader:
	"""\
	Read a request encoded with multipart/form-data
	"""
	def __init__(self, request:'ClientRequest', response:ServerResponse, autoreject:bool):
		self.request = request
		self.response = response
		self.cl_con = request.cl_con
		self.autoreject:bool = autoreject

		# This flips to True when the entire form stream was read
		self.finished = False

		self.boundary:str = jag_http_ents.HTTPHeaderKV(
			self.request.headers['content-type']
		)['boundary']

		if not self.boundary:
			if self.autoreject:
				self.request.reject(400, 'Missing boundary declaration')
				raise StopExecution(
					'Stopped execution due to invalid form boundary'
				)
			else:
				raise InvalidFormData(
					'Invalid Multipart Form data: No boundary present'
				)

		self.boundary = b'--' + self.boundary.encode()
		self.boundary_len = len(self.boundary)

		# Trailing data from the last field
		self.trailing_data:bytes = b''

	def __enter__(self):
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		pass

	def yield_trailing(self):
		tdata = self.trailing_data
		self.trailing_data = b''
		return tdata

	def next_field(self) -> MultipartFormField|None:
		"""\
		Traverse to the next field,
		skipping the previous one if it wasn't read.
		"""
		if self.finished:
			# todo: better error message
			raise TypeError(
				"""The form stream has come to an end. There's no more data to read"""
			)

		with ByteSequenceStopper(self.boundary) as lookup:
			while True:
				found, trailing = lookup.feed(
					# self.cl_con.recv(4096)
					self.cl_con.recv(
						min(len(self.boundary), 32)
					)
				)
				if found:
					break

			# todo: fuck
			td_match = trailing[:2]
			# important todo: Not all browsers add '--' as prefix/suffix

			# We always need the trailing 2 bytes of the boundary
			if len(td_match) < 2:
				# todo: this is absolutely retarded
				# BUT this should happen rarely enough to ignore
				more_trailing = self.cl_con.makefile('rb')
				td_match += more_trailing.read(1)
				more_trailing.close()

			# if there's an extra '--' after boundary - it's the end of the message
			if td_match == b'--':
				self.finished = True
				return None

			return MultipartFormField(
				self.request,
				self.response,
				self,
				HeaderFields(self.cl_con, prefix_data=trailing),
				self.autoreject
			)



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


