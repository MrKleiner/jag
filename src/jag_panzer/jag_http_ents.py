"""
This file contains most of the useful HTTP entities, like
Caching
Cors
Content Negotiation
OPTIONS negotiation
Cookies
Accept
"""

import datetime, string, io, hashlib
from pathlib import Path
import jag_util


class HTTPHeaderKV:
	"""\
	HTTP Header Key-Value format:
	Cache-Control: key=value, key, key=value
	"""

	kv_dict:dict = {}

	def __init__(self, input_data=None, delimeter:str='; ', smart:bool=False):
		self.accepted_types = (str, bytes, HTTPHeaderKV, dict, type(None))
		if not type(input_data) in self.accepted_types:
			raise TypeError(f'Input header kv type must be one of {self.accepted_types}, not {type(input_data)}')

		if type(input_data) in (str, bytes):
			if isinstance(input_data, bytes):
				input_data = input_data.decode()
			self.kv_dict_from_string(input_data, delimeter=delimeter, smart=smart)

		if isinstance(input_data, dict):
			self.kv_dict = input_data

		if isinstance(input_data, HTTPHeaderKV):
			self.kv_dict = input_data.kv_dict


	# Consume input
	# =======================
	def kv_dict_from_string_smart(self, kvstring:str):
		kname = self.kv_dict.get('fuck')
		for c in kvstring:
			break

	def kv_dict_from_string(self, kvstring:str, delimeter:str='; ', smart:bool=False):
		if smart:
			self.kv_dict_from_string_smart(kvstring)
			return

		pairs = kvstring.split(delimeter)
		for pair in pairs:
			p_split = pair.split('=')
			if len(p_split) == 1:
				self.kv_dict[p_split[0]] = True
				continue
			if len(p_split) > 1:
				self.kv_dict[p_split[0]] = p_split[1]


	# Dump
	# =======================
	def __str__(self):
		pairs = []
		for k, v in self.kv_dict.items():
			if v == True:
				pairs.append(k)
				continue
			if v in (False, None):
				continue
			pairs.append(
				'='.join((k, str(v)))
			)
		return '; '.join(pairs)


	# Edit
	# =======================
	def __getitem__(self, key):
		return self.kv_dict[key]
	def __setitem__(self, key, val):
		self.kv_dict[key] = val
	def __delitem__(self, key):
		del self.kv_dict[key]
	def __iter__(self):
		for k, v in self.kv_dict.items():
			yield k, v
	def __contains__(self, value):
		return value in self.kv_dict







class HTTPHeaders:
	"""\
	A set of HTTP headers, excluding startline.

	input_data is treated according to type:
	    - list|tuple|set: a list of raw encoded/decoded header fields, eg b'Cache-Control: no-store\r\n'
	    - dict: Header Name: Header Content

	Internally all keys are stored in lowercase:
	    Cache-Control -> cache-control

	When dump is requested - they're converted back to capital:
	    cache-control -> Cache-Control

	Header fields could have repeating headers with different values.
	This occasion is not very common, therefore:
	    - __getitem__ would return the first header matching the target name.
	      None is returned if no header with this name was found.
	    - __iter__ would iterate over every single header.
	    - __setitem__ would ADD a new header, if no header with the same name and value exists.
	    - get_all(name) would return a list of all the attributes matching the name.
	"""



	fields:set = set()

	def __init__(self, input_data=None):
		self.accepted_types = (list, tuple, set, HTTPHeaders, dict, type(None))
		if not type(input_data) in self.accepted_types:
			raise TypeError(f'Input fields type must be one of {self.accepted_types}, not {type(input_data)}')

		if type(input_data) in (list, tuple, set):
			self.fields_from_array(input_data)

		if isinstance(input_data, dict):
			self.fields_from_dict(input_data)

		if isinstance(input_data, HTTPHeaders):
			self.fields = input_data.fields


	# Shared util
	# =======================
	@staticmethod
	def field_to_kv(field:bytes|str):
		"""\
		b'Cache-Control: no-store\r\n'
		to
		('cache-control', 'no-store')
		"""
		if isinstance(field, bytes):
			field = field.decode()
		field = field.strip()

		field_split = field.split(': ')

		return field_split[0].lower(), ': '.join(field_split[1:])


	# Consuming input data
	# =======================
	def fields_from_array(self, flist:list|tuple|set):
		"""\
		[b'Cache-Control: no-store\r\n', ...]
		to
		[('cache-control', 'no-store'), ...]
		"""
		for field in flist:
			self.fields.add(
				self.field_to_kv(field)
			)

	def fields_from_dict(self, fdict:dict):
		"""
		{'Cache-Control': 'no-store', ...}
		to
		[('cache-control', 'no-store'), ...]
		"""
		for k, v in fdict.items():
			if isinstance(k, bytes):
				k = k.decode()
			if isinstance(v, bytes):
				v = v.decode()

			self.fields.add(
				(k.lower(), str(v))
			)


	# Getting headers
	# =======================
	def __getitem__(self, tgt_hname:str):
		"""Get first occurance of the header with the specified name"""
		tgt_hname = str(tgt_hname).lower()
		for hname, hval in self.fields:
			if tgt_hname == hname:
				return hval

		return None

	def __iter__(self):
		"""Iterate over all headers"""
		for header in self.fields:
			yield header

	def __setitem__(self, key:str, value):
		"""ADD a header to the list IF no identical k:v pair exist"""
		self.fields.add(
			(str(key).lower(), value,)
		)

	def __delitem__(self, key):
		"""Delete first occurance of the header with the specified name"""
		key = str(key).lower()
		for hname, hval in self.fields:
			if key == hname:
				self.fields.remove((hname, hval,))

	def __contains__(self, key):
		key = str(key).lower()
		for hname, hval in self.fields:
			if key == hname:
				return True
		return False

	def get_all(self, hname:str):
		"""Return a list of all the headers matching the requested name"""
		hname = str(hname).lower()
		return [(hn, hv) for hn, hv in self.fields if hn == hname]


	# Dumping headers
	# =======================
	def progrssive_construct(self, add_rn:bool=True):
		"""\
		Dump headers into socket.sendall() ready format.
		- rn:bool=True Whether to append '\r\n' to the end of each header
		"""
		# Trying to save a few microseconds...
		if add_rn:
			for hname, hval in self.fields:
				yield f"""{string.capwords(hname, '-')}: {str(hval)}\r\n""".encode()
		else:
			for hname, hval in self.fields:
				yield f"""{string.capwords(hname, '-')}: {str(hval)}""".encode()

	def __bytes__(self):
		"""
		Return a bytes object representing all headers.
		WITHOUT double \r\n in the end.
		"""
		buf = io.BytesIO()
		for header in self.progrssive_construct():
			buf.write(header)
		return buf.getvalue()





class HTTPDateTime:
	"""\
	HTTP Date object.
	Capable of parsing HTTP Date into datetime.datetime and vise versa.
	- input_data:str|datetime.datetime|int|HTTPDateTime

	The input data is evaluated based on type:
	    - str: HTTP Date, eg "Tue, 22 Feb 2022 22:22:22 GMT"
	    - datetime.datetime: regular datetime object
	    - int: UNIX time (2038 is coming)
	    - HTTPDateTime: simply pull info from another HTTPDateTime object

    In the end of the day everything above
    gets evaluated into datetime.datetime

    By default, everything is UTC.

    Pro tip: UTC = GMT
	"""
	

	def __init__(self, input_data=None):
		self.accepted_types = (str, int, datetime.datetime, type(None), None, HTTPDateTime)
		if not type(input_data) in self.accepted_types:
			raise TypeError(f'Input Date should be one of {self.accepted_types}, not {type(input_data)}')

		# datetime from HTTP Date
		if isinstance(input_data, str):
			self.dtime = self.dtime_from_http_date(input_data)
		# datetime from datetime
		if isinstance(input_data, datetime.datetime):
			self.dtime = self.as_utc(input_data)
		# datetime from UNIX time
		if isinstance(input_data, int):
			self.dtime = self.dtime_from_unix_stamp(input_data)
		# from another HTTP Date class
		if isinstance(input_data, HTTPDateTime):
			self.dtime = input_data.dtime

		# init new datetime
		if input_data is None:
			self.dtime = datetime.datetime.now(datetime.timezone.utc)

		# initial time
		self.src_time = self.dtime

	# Consuming input data
	# =======================
	@staticmethod
	def as_utc(dtime:datetime.datetime):
		"""Return datetime as UTC timezone"""
		return dtime.astimezone(datetime.timezone.utc)

	@classmethod
	def dtime_from_http_date(cls, dtime_string:str):
		"""HTTP Date string to datetime.datetime in UTC"""
		return cls.as_utc(
			datetime.datetime.strptime(dtime_string, '%a, %d %b %Y %H:%M:%S %Z')
		)

	@classmethod
	def dtime_from_unix_stamp(cls, unix_stamp:int):
		"""UNIX integer timestamp to datetime.datetime in UTC"""
		return cls.as_utc(
			datetime.datetime.fromtimestamp(unix_stamp)
		)


	# Util
	# =======================
	@staticmethod
	def time_to_seconds(days:int=0, hours:int=0, minutes:int=0, seconds:int=0, weeks:int=0) -> int:
		"""\
		days, hours, minutes ...
		to seconds
		"""
		return (
			(days*86400)
			+
			(hours*3600)
			+
			(minutes*60)
			+
			seconds
			+
			(weeks*604800)
		)


	# Operations
	# =======================
	def add(self, days=0, hours=0, minutes=0, seconds=0, weeks=0):
		"""Add a certain amount of time to the Date"""
		self.dtime += datetime.timedelta(
			days=days,
			hours=hours,
			minutes=minutes,
			seconds=seconds,
			weeks=weeks
		)

	def subtract(self, days=0, hours=0, minutes=0, seconds=0, weeks=0):
		"""Subtract a certain amount of time from the Date"""
		self.dtime -= datetime.timedelta(
			days=days,
			hours=hours,
			minutes=minutes,
			seconds=seconds,
			weeks=weeks
		)


	# Dumping
	# =======================
	def __str__(self):
		"""Return HTTP Date string"""
		# return self.dtime.strftime('%a, %d %b %Y %H:%M:%S %Z')
		return self.dtime.strftime('%a, %d %b %Y %H:%M:%S') + ' GMT'


	# Comparisons
	# =======================
	def _comparator(self, other, operator:str):
		"""compare two HTTP dates"""
		try:
			other = HTTPDateTime(other)
			if operator == '==':
				return self.dtime == other.dtime
			if operator == '!=':
				return self.dtime != other.dtime
			if operator == '<=':
				return self.dtime <= other.dtime
			if operator == '>=':
				return self.dtime >= other.dtime
			if operator == '>':
				return self.dtime > other.dtime
			if operator == '<':
				return self.dtime < other.dtime
		except TypeError as e:
			raise TypeError(f'The comparison target should be one of {self.accepted_types}, not {type(other)}')

	def __lt__(self, other):
		self._comparator(other, '<')
	def __gt__(self, other):
		self._comparator(other, '>')
	def __le__(self, other):
		self._comparator(other, '<=')
	def __ge__(self, other):
		self._comparator(other, '>=')
	def __eq__(self, other):
		self._comparator(other, '==')
	def __ne__(self, other):
		self._comparator(other, '!=')



"""
Client: Requesting image.
Server: Image not ready yet (does not exist). Code 404
        Cache-Control: max-age: 300 (5 minutes)

Client: Requesting image.
        If-Modified-Since: Date
Server: * checks resource mod time *
        * compares dates *
        * sends 304 or 200 *
        Cache-Control: max-age: (1 day)
        Last-Modified: date
        Date: date
        Etag: hash

Client: Requesting image.
        If-None-Match: hash
        If-Modified-Since: Date
Server: * compares dates *
        IF dates match
            * compares hashes *
        * sends 304 or 200 *
"""




class HTTPClientCacheControl:
	"""\
	Control the way server responses are cached on the client
	according to HTTP Caching spec.
	https://developer.mozilla.org/en-US/docs/Web/HTTP/Caching

	This class is only responsible for 
	sending non-strict commands to the client
	and has little to no effect on the server.

	Some of the completely useless conditions are not implemented,
	like caching based on language.
	"""

	# True state will cause the (possibly) personalized response to only be stored
	# with the specific client and not be leaked to any other user of the cache.
	
	# False would indicate that the response
	# can be stored in a shared cache.
	# Responses for requests with Authorization header fields
	# must not be stored in a shared cache;
	# however, the public directive will cause such responses
	# to be stored in a shared cache.
	# AKA, ok for icons/css, bad for sensitive data/nude pics.

	# None = do not include private/public
	# True = include private
	# False = include public
	private = None
	# public = False

	# The must-revalidate response directive indicates
	# that the response can be stored in caches
	# and can be reused while fresh. If the response becomes stale,
	# it must be validated with the origin server before reuse.
	must_revalidate = False

	# The no-store response directive indicates that
	# any caches of any kind (private or shared) should not store this response.
	no_store = False

	# The immutable response directive indicates
	# that the response will not be updated while it's fresh.
	immutable = False

	# stale-while-revalidate

	# The max-age=N request directive indicates that the client
	# allows a stored response that is generated on the
	# origin server within N seconds - where N may be
	# any non-negative integer (including 0).
	max_age = None

	etag_enabled = False

	# Enable "Date" header in the response
	date_stamp_enabled = True





class HTTPCachedResource:
	"""
	Represents any kind of response resource that is supposed to be cached.
	"""

	def __init__(self, request_headers:HTTPHeaders, response_headers:HTTPHeaders, cl_caching:HTTPClientCacheControl):
		self.request_headers =  request_headers
		self.response_headers = response_headers
		self.cl_caching =       cl_caching

		self.datenow = HTTPDateTime()

		# todo: there HAS to be a better way of doing this
		self.private =            cl_caching.private
		self.must_revalidate =    cl_caching.must_revalidate
		self.no_store =           cl_caching.no_store
		self.immutable =          cl_caching.immutable
		self._max_age =           cl_caching.max_age
		self.upd_cache_ctrl_header()
		self.etag_enabled =       cl_caching.etag_enabled
		self.date_stamp_enabled = cl_caching.date_stamp_enabled


	def info_from_file(self, file:str|Path|bytes, etag=None):
		"""\
		Get caching info from file path, such as:
			- Last-Modified
			- Etag
		"""
		if isinstance(file, bytes):
			file = file.decode()

		file = Path(str(file))
		if not file.is_file():
			raise FileNotFoundError(f'The target file {str(file)} does not exist')

		info = file.stat()

		self.response_headers['last-modified'] = HTTPDateTime(info.st_mtime)

		if (self.etag_enabled and etag != False) or etag == True:
			with open(str(file), 'rb') as fbuf:
				self.response_headers['etag'] = jag_util.progrssive_hash(fbuf, hashlib.md5, 50)

	def max_age(self, days=0, hours=0, minutes=0, seconds=0, weeks=0):
		"""Set max age of a response resource"""
		if days + hours + minutes + seconds + weeks:
			self._max_age = HTTPDateTime.time_to_seconds(days, hours, minutes, seconds, weeks)

			self.upd_cache_ctrl_header()

	def upd_cache_ctrl_header(self):
		"""rebuild cache control response header"""
		del self.response_headers['cache-control']

		self.response_headers['cache-control'] = HTTPHeaderKV({
			'private': self.private,
			'public': not self.private,
			'max-age': self._max_age,
			'must_revalidate': self.must_revalidate,
			'immutable': self.immutable,
			'no-store': self.no_store,
		})



	# Properties
	# =======================
	@property
	def private(self):
		return self.private
	@private.setter
	def private(self, state):
		self.private = state
		self.upd_cache_ctrl_header()


	@property
	def must_revalidate(self):
		return self.must_revalidate
	@must_revalidate.setter
	def must_revalidate(self, state):
		self.must_revalidate = state
		self.upd_cache_ctrl_header()


	@property
	def immutable(self):
		return self.immutable
	@immutable.setter
	def immutable(self, state):
		self.immutable = state
		self.upd_cache_ctrl_header()


	@property
	def no_store(self):
		return self.no_store
	@no_store.setter
	def no_store(self, state):
		self.no_store = state
		self.upd_cache_ctrl_header()


	@property
	def date_stamp_enabled(self):
		return self._date_stamp_enabled
	@date_stamp_enabled.setter
	def date_stamp_enabled(self, state):
		del self.response_headers['date']

		self._date_stamp_enabled = False
		if state:
			self.response_headers['date'] = self.datenow
			self._date_stamp_enabled = True




class AccessControl:
	"""\
	Access Control Params.
	Used to respond to OPTIONS and external requests.

	Pro tip: Technically, this does absolutely nothing,
	this is only needed to control browser's automatic behaviour.
	"""

	# A list of external origins allowed to access the requested resource
	# This is ONLY used when an EXTERNAL ORIGIN is trying to access the resource
	# Syntax:
	"""
	('http://url', 'https://url', ...)
	"""
	allow_origins = '*'

	# e.g. sourcetricks.eu
	home_origin:str|None = None

	# indicate which response headers should be made available to js scripts
	# running in the browser, in response to a cross-origin request.
	# Syntax: ['header-name', 'header-name' ...] OR '*'
	expose_headers:list[str]|tuple[str]|set[str]|str = None

	# Tell browsers whether to expose the response
	# to the frontend JavaScript code
	# when the request's credentials mode(Request.credentials) is include.
	allow_credentials:str = None

	# whether to respond to the OPTIONS requests automatically
	# and omit user function execution
	options_auto_negotiation:bool = True

	def __init__(self, request_headers:HTTPHeaders, response_headers:HTTPHeaders):
		self.request_headers = request_headers
		self.response_headers = response_headers

	def apply_headers(self):
		"""\
		This is not needed for simple GET requests.
		Only preflighted (OPTIONS, ...) requests and extrenal origin requests need this info.
		"""

		if self.expose_headers and 'Access-Control-Request-Headers' in self.request_headers:
			self.response_headers['Access-Control-Expose-Headers'] = '*' if self.expose_headers == '*' else ', '.join(self.expose_headers)

		if self.allow_credentials is not None:
			self.response_headers['Access-Control-Allow-Credentials'] = str(self.allow_credentials).lower()

		# This only works if "Origin" header is present in the request
		request_origin = self.request_headers['origin']
		if self.allow_origins and request_origin:
			if self.allow_origins == '*':
				self.response_headers['Access-Control-Allow-Origin'] = '*'
			elif type(self.allow_origins) in (list, tuple, set):
				if request_origin.lower() in self.allow_origins:
					self.response_headers['Access-Control-Allow-Origin'] = request_origin




class CORSAllowance:
	"""\
	Control browser's CORS behaviour.

	This is only needed when a client requests, lets say index.html,
	aka signal the browser which urls it may try connecting to
	in the first place.
	
	``'self'`` IS A SEPARATE BOOLEAN

	Syntax::

	    [
	        ( '<directive>', ('url', 'url' ...) ),
	        ( 'connect-src', ('url', 'url' ...) ),
	    ]
	"""

	# The policy declaration itself
	policy:list[tuple[str, tuple[str]]] = None

	# This should always be True, unless there are some VERY specific needs
	include_self:bool = True


	def __init__(self):
		"""\
		Init method precaches the CORS string as it may be quite large
		and (presumably) never changes while the server is running.
		"""
		self.cors_string = ''

		if self.policy:
			for directive, urls in self.policy:
				self.cors_string += directive
				if self.include_self:
					self.cors_string += """ 'self' """
				self.cors_string += ' '.join(urls)
				self.cors_string += '; '

	def apply_to_headers(self, headers:HTTPHeaders):
		if self.policy:
			headers['Content-Security-Policy'] = self.cors_string




# trac_form_token=86adf94183eef80ca7c0d594; trac_session=824a0c6ad224fe65bfedea53

class Cookies:
	""" BISCUITS """
	def __init__(self, request_headers:HTTPHeaders, response_headers:HTTPHeaders):
		init_data = request_headers['cookie']
		self.request_cookies:HTTPHeaderKV = HTTPHeaderKV(init_data)
		self.response_headers:HTTPHeaders = response_headers
		# self.response_cookies = HTTPHeaderKV()


	def add_cookie(self, cname, cval, params:dict|None=None):
		"""\
		Adds one Set-Cookie header per call.
		"expires" parameter accepts datetime objects.
		"""
		params = params or {}
		cookie_params = {
			'domain': None,
			'expires': None,
			'secure': None,
			'path': None,
			'httponly': False,
			'max_age': None,
			'samesite': None,
		} | params

		expires = cookie_params['Expires']
		if expires:
			cookie_params['Expires'] = HTTPDateTime(expires)

		self.response_headers['set-cookie'] = f'{cname}={cval}; {str(HTTPHeaderKV(cookie_params))}'



class ByteRange:
	"""\
	Utilities for managing byterange requests and responses.
	"""
	def __init__(self, data):
		pass














