
"""
wss
"""


"""
Websockets are funny.
They're cool, but, as is it usually is with web tech - retarded.

The concept is simple on paper: ping-pong payloads with headers.

Each time a payload is sent in either direction - 
    it has to be "initialized/identified" with a frame (basically a header)
    the frame specifies the payload size and so on.

    The payload could be sent through multiple frames.
    The frame should simply signal whether it's
    a first, continuation or last frame in the series.


# -------------------
#     Frame RFC
# -------------------


 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-------+-+-------------+-------------------------------+
|F|R|R|R| opcode|M| Payload len |    Extended payload length    |
|I|S|S|S|  (4)  |A|     (7)     |             (16/64)           |
|N|V|V|V|       |S|             |   (if payload len==126/127)   |
| |1|2|3|       |K|             |                               |
+-+-+-+-+-------+-+-------------+ - - - - - - - - - - - - - - - +
|     Extended payload length continued, if payload len == 127  |
+ - - - - - - - - - - - - - - - +-------------------------------+
|                               |Masking-key, if MASK set to 1  |
+-------------------------------+-------------------------------+
| Masking-key (continued)       |          Payload Data         |
+-------------------------------- - - - - - - - - - - - - - - - +
:                     Payload Data continued ...                :
+ - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - +
|                     Payload Data continued ...                |
+---------------------------------------------------------------+

"""


# -------------------
#  Long story short
# -------------------

# Even though they're called "frames" - it's actually just a payload
# with a header.
# It's as simple as [<header><data>]
#                   ^^^^^^^^^^^^^^^^
#                    payload(frame)

"""
The payload header contains:
  - Flags
      4 bits acting as an array of booleans.
  - Opcode
      Another 4 bits acting as a single code.
  - Payload len
      The size of the payload, not including the frame (obviously).
  - Masking-key
      By default WSS payloads are XORed (cyclic).
      This data contains the key to unmask the payload.


# -------------------
#       Flags
# -------------------
There are 4 possible flags, stored in the first 4 bits of the header.
Browsers (so far) only recognize the first one, indicating whether this frame
is the last frame in the series of frames or not.

- 1000****
  ^
  FIN flag: Identifies whether the payload is
  the last payload in the series.

- 0111****
   ^^^
  Reserved flags for future use. Garbage.
  Websockets have been around since
  the very beginning of HTML5 and these flags
  are still not used AND not exposed in any browser.



# -------------------
#       Opcode
# -------------------
Opcode consists of 4 bits and comes immediately after the flag bits.
While flags represent an array of booleans in order,
opcode is enterpreted as a single code, like 1011

The values recognized by browsers are:
- 0x0: continuation frame of the same message.
- 0x1: The message consists of text decodable with UTF-8.
- 0x2: The message consists of binary data.
- 0x8: The message indicates that the connection should be closed.
- 0x9: Payload is a ping.
- 0xA: Payload is a pong.
       For pings and pongs, the max payload length is 125.
       THIS SHIT IS NOT RECOGNIZED BY ANY BROWSER,
       Even though the spec crearly states that they should...



# -------------------
#    Payload len
# -------------------
It's absolutely retarded.
A complex system was introduced to save 3 bytes per frame.

1 - Read bits 9-15 (inclusive) and interpret that as an unsigned integer.
    If it's 125 or less, then that's the length; you're done.
    If it's 126, go to step 2. If it's 127, go to step 3.

2 - Read the next 16 bits and interpret those as an unsigned integer.
    You're done.

3-  Read the next 64 bits and interpret those as an unsigned integer.
    (The most significant bit must be 0.) You're done.

The total size of a single message is NOT revealed anywhere.


# -------------------
#      Masking
# -------------------
Browsers XOR the data of the payload by default.

The spec sez it's to avoid confusion on any servers
in the middle of the WSS server and web client, but in reality
this is just some useless garbage excessively
wasting server resources.
This behaviour can be avoided when using custom WSS clients,
but it's ONN by default in every browser

Masking key consists of 4 bytes which come immediately after payload length.
Cyclic loop is used to encode/decode the payload:

Mask: 0 1 2 3 4 0 1 2 3 4 ...
Data: 0 1 2 3 4 5 6 7 8 9 ...

"""



"""
A message can consist of multiple frames.

+-------------------------------------------------------+
|                     MESSAGE                           |
|                                                       |
|      FRAME           FRAME           FRAME            |
|  +------------+  +------------+  +------------+       |
|  |   HEADER   |  |   HEADER   |  |   HEADER   |       |
|  +------------+  +------------+  +------------+  ...  |
|  |    DATA    |  |    DATA    |  |    DATA    |       |
|  +------------+  +------------+  +------------+       |
+-------------------------------------------------------+
"""





# There's something deeply wrong with how this package imports things

from pathlib import Path
import sys
# print('WSS sys path BEFORE tweaks:', *sys.path, sep='\n')
sys.path.append(str(Path(__file__).parent.parent))
# print('WSS sys path AFTER tweaks:', *sys.path, sep='\n')

from jag_util import clamp as clamp_num





# use the first fastest algorithm for XORing
# benchmarks:
# XORing 80mb worth of content on an SBC
# (worst case scenario. Divide this by ~50 for XEON servers):
# 
#                               Max speed = not slower than regular SFTP + 
#                                           absolute maximum achievable utilizing
#                                           all the possible tricks in python language
# C -       8.5 sec             (100%  of max speed)
# xor lib - 26 sec              (32.7% of max speed)
# numpy -   37 sec (+14mb RAM)  (22.9% of max speed)
# default - 145 sec             (5.86% of max speed)

# The way the algorythm is chosen is simple:
# There's some hard coded sample data:
# 	- 8 random bytes acting as a payload BEFORE XORing
# 	- 4 random bytes acting as a mask
# 	- sha256 hex hash digest of the sample payload AFTER XORing
# Then, a number of algorythms are tried in the following order:
#	- Fastest C
# 	- XOR Lib
# 	- numpy
# 	- default python
# Each attempt wrapped inside try/except block tries XORing with sample data
# and in the end there's an assert comparing hex digests of the newly generated result.
# If nothing goes wrong and hashes match - the method is used.
# Default python method is used as a fallback if all the attempts fail.
class masking_algo:
	def __init__(self, session):
		import sys, platform
		self.session = session
		self.byteorder = sys.byteorder
		self.sample_data = {
			'data': bytes([26, 222, 201, 231, 84, 132, 89, 231]),
			'mask': bytes([87, 132, 89, 231]),
			'hash': '2e383fddf78d1acc795830f56b4ec6464e408c418e67add6fa4c017afa618963',
		}

		platform_name = platform.system().lower()

		# First - try the c implementation
		try:
			if 'linux' in platform_name:
				from wss_boost.linux.websockets import speedups
			else:
				from wss_boost.win.websockets import speedups

			test_apply = speedups.apply_mask(self.sample_data['data'], self.sample_data['mask'])

			assert self.session.hashlib.sha256(test_apply).hexdigest() == self.sample_data['hash']

			self.fast_c = speedups.apply_mask
			self.apply_mask = self.c_fastest

			self.sample_data = None

			print('Using fast C')

			return
		except Exception as e:
			pass

		# Didn't work - try xor lib
		try:
			from xor_cipher import cyclic_xor
			test_apply = cyclic_xor(self.sample_data['data'], self.sample_data['mask'])
			assert self.session.hashlib.sha256(test_apply).hexdigest() == self.sample_data['hash']

			self.cyclic_xor = cyclic_xor
			self.apply_mask = self.xor_lib

			self.sample_data = None

			print('Using xor lib')

			return
		except Exception as e:
			pass

		# Didn't work - try numpy
		try:
			import numpy as np
			resmask = np.resize(np.fromstring(self.sample_data['mask'], dtype='uint8'), len(self.sample_data['data']))
			data_array = np.fromstring(self.sample_data['data'], dtype='uint8')
			test_apply = np.bitwise_xor(data_array, resmask).tobytes()
			assert self.session.hashlib.sha256(test_apply).hexdigest() == self.sample_data['hash']

			self.numpy = np
			self.apply_mask = self.numpy_fast

			self.sample_data = None

			print('Using numpy')

			return
		except Exception as e:
			pass

		# sadly - fall back to default
		self.apply_mask = self.default_slow
		print('Using default')
		self.sample_data = None


	# the slowest method possible
	def default_slow(self, data, mask):
		# 40% speedup from original approach
		bt_array = bytearray(data)
		for idx in range(len(bt_array)):
			bt_array[idx] ^= mask[idx%4]

		return bytes(bt_array)

	# Numpy is 3 times faster than default method
	def numpy_fast(self, data, mask):
		np = self.numpy

		resmask = np.resize(np.fromstring(mask, dtype='uint8'), len(data))
		data_array = np.fromstring(data, dtype='uint8')

		return np.bitwise_xor(data_array, resmask).tobytes()

	# There's a library implementing faster XOR. It's 11% faster than numpy
	# Numpy wastes 14mb of ram which is just too much. Xor Lib is preferred over numpy...
	# It's overall much lighter than numpy, because numpy holds an entire structure underneath
	# While XOR Lib is simply a few C functions
	def xor_lib(self, data, mask):
		return self.cyclic_xor(data, mask)

	# The pure C implementation is the fastest method and is 8 times faster than xor lib
	def c_fastest(self, data, mask):
		return self.fast_c(data, mask)




# Default params of a WSS session
class wSessionDefaults:
	recv_as_stream = False
	send_chunksize = 4096
	recv_chunksize = 4096
	msg_max_size = (1024**2)*32
	masked_response = False



# important todo: https://youtu.be/m_a0fN48Alw
# !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

# important todo: write a python library in C with super simple functions, like fast XOR and fast number clamp.

# important todo: there's a built-in feature to make function change upon triggering
# aka it's no longer needed to replace the class method with a lambda
class wss_session:
	"""
	Standard WSS session.
	- connection:socket.socket client connection.
	- incoming_hshake:list=None
	    List representing header fields in HTTP format: ['Key: Value'].
	    If left None - the session would try getting the header fields
	    from the client.
	    If a list representing a valid WSS switch request is passed - 
	    the session would send a WSS handshake response.
	"""
	def __init__(self, connection, incoming_hshake=None):

		# import some commonly used libs
		import base64, json, hashlib, io, struct, sys, collections, os, socket, secrets
		from pathlib import Path
		self.collections = collections
		self.sys = sys
		self.Path = Path
		self.struct = struct
		self.io = io
		self.base64 = base64
		self.json = json
		self.hashlib = hashlib
		self.os = os
		self.socket = socket
		self.secrets = secrets

		# defaults
		self.defaults = wSessionDefaults()
		# client connection
		self.connection = connection

		# choose the best masking algo available
		decision = masking_algo(self)
		self.apply_mask = decision.apply_mask

		# aligned receive solution
		if self.os.name == 'posix':
			self.aligned_receive = self.aligned_recv_linux
		else:
			self.aligned_receive = self.aligned_recv_windows

		# respond to the client with a wss handshake
		self.respond_handshake(incoming_hshake)
		# make sure it never happens again
		self.respond_handshake = lambda: None



	# Aligned receive
	# =================

	# Receive an exact amount of data

	# The bufsize argument passed to .recv()
	# only specifies the MAXIMUM amount of data to receive.
	# aka .recv(512) could easily return 357 bytes.
	# On UNIX (Linux) platforms it's possible to add socket.MSG_WAITALL
	# flag to wait for the entire buffer to fill (all 512 bytes).
	# But this is not possible on Windows.
	# A retarded while loop has to be implemented to make this work
	# on Windows.
	# This is why you should never use windows for hosting.

	# You will get hacked and get cancer of the left asscheek.

	# aligned_receive
	def aligned_recv_windows(self, bufsize, chunk_size=8192):
		# Shouldn't this print a warning or something ?
		if bufsize <= 0:
			return b''

		# Creating an io.BytesIO buffer to receive 2 bytes
		# is MUCH slower than simple concatenating (b'' + ...)
		# Through tests it was determined that there's no need to
		# create a buffer for receiving less than 512 bytes.
		# todo: Lower the number a little bit just to be sure?
		if bufsize < 512:
			buf = b''
			# print('Need to receive:', bufsize)
			while True:
				# todo: raise a warning when the result is actually longer
				# than anticipated
				if len(buf) >= bufsize:
					# print('DROP')
					return buf

				# print('equasion', max(1, min(chunk_size, bufsize-len(buf))))
				# data = self.connection.recv(max(1, min(chunk_size, bufsize-len(buf))))
				data = self.connection.recv(
					clamp_num(chunk_size, 1, bufsize-len(buf))
				)
				buf += data
				# print('Received:', str(len(data)).ljust(20), 'target:', str(bufsize).ljust(20), 'has:', str(len(buf)).ljust(20), 'want:', str(max(1, min(chunk_size, length-len(buf)))).ljust(20))
		else:
			buf = self.io.BytesIO()
			while True:
				if buf.tell() >= bufsize:
					return buf.getvalue()

				# data = self.connection.recv(max(1, min(chunk_size, bufsize-buf.tell())))
				data = self.connection.recv(
					clamp_num(chunk_size, 1, bufsize-buf.tell())
				)
				buf.write(data)

	def aligned_recv_linux(self, bufsize, chunk_size=None):
		return self.connection.recv(bufsize, self.socket.MSG_WAITALL)



	# Automated
	# =================
	def respond_handshake(self, incoming_hshake):
		lines = None
		# If header fields were not provided on session init - 
		# it means they have to be retrieved from the client.
		if not incoming_hshake:
			from jag_http_session import headerFields
			header_buffer = headerFields(self.connection, 65535)
			header_buffer.collect()
			lines = header_buffer.lines
		elif type(incoming_hshake) in (list, tuple, set):
			lines = list(incoming_hshake)

		if not lines:
			raise Exception(f'Could not evaluate incoming WSS handshake {lines}, {incoming_hshake}')

		if lines[0].startswith('GET '):
			del lines[0]

		# evaluate these headers into a dict for easier use
		hshake_info = {}
		for ln in lines:
			splitline = ln.split(': ')
			hshake_info[splitline[0].strip().lower()] = ': '.join(splitline[1:]).strip()

		# construct a response
		resolve = {
			'Upgrade': 'websocket',
			'Connection': 'Upgrade',
		}

		# The handshake itself.
		# The spec sez that requests without this handshake must be rejected.
		# Jag doesn't do that
		if 'sec-websocket-key' in hshake_info:
			self.input_wss_key = hshake_info['sec-websocket-key']
			self.output_wss_key = self.hashlib.sha1(
				(hshake_info['sec-websocket-key'] + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()
			)
			# important todo: is this magic string actually important ?
			# aka could it be any other string ?
			resolve['Sec-WebSocket-Accept'] = self.base64.b64encode(self.output_wss_key.digest()).decode()

		self.connection.sendall(b'HTTP/1.1 101 Switching Protocols\r\n')
		for key in resolve:
			self.connection.sendall(f"""{key}: {resolve[key]}\r\n""".encode())
		self.connection.sendall(b'\r\n')



	# Interface
	# =================

	# terminate WSS session
	def terminate(self, reason=b'piss'):
		# raise NotImplementedError()
		# print('terminating, because', reason)
		# self.connection.sendall(self.construct_frame(reason, 0x1))
		self.connection.close()
		# self.sys.exit()

	# Receive a message
	def recv_message(self, as_stream:bool=None, maxsize:bool=None, chunksize:bool=None):
		"""
		Receive a message from the client.
		- as_stream:bool=None 
		    Whether to receive the message as a stream or all at once.
		- maxsize:int
		    Maximum size of the received message
		"""
		msg_receiver = wssMessageReceiver(
			self,
			maxsize or self.defaults.msg_max_size,
			chunksize or self.defaults.recv_chunksize
		)
		as_stream = as_stream if as_stream != None else self.defaults.recv_as_stream
		if not as_stream:
			buf = self.io.BytesIO()
			for chunk in msg_receiver.data_stream():
				buf.write(chunk)
			return buf.getvalue()

		return msg_receiver.data_stream()

	# Send a message
	# Simply send a message, with no extra fuckery
	def send_message(self, data, msg_type:str='binary', chunksize:bool=None, masked:bool=None):
		"""
		Send a WSS message
		- data:bytes|buffer
			Data to send.
			If buffer is specified - chunksize is used
		"""
		masked = masked if masked != None else self.defaults.masked_response

		if isinstance(data, bytes):
			with wssMessageSender(self, masked, msg_type) as msg:
				msg.send_data(data, True)
			return
		else:
			chunksize = chunksize if chunksize != None else self.defaults.send_chunksize
			msg_len = data.seek(0, 2)
			sent = 0
			data.seek(0, 0)
			with wssMessageSender(self, masked, msg_type) as msg:
				while True:
					chunk = data.read(chunksize)
					sent += chunk
					if msg_len == sent:
						msg.send_data(data, True)
						break
					else:
						msg.send_data(data, False)

	# Stream a message of unknown size
	def stream_message(self, msg_type:str='binary', masked:bool=None):
		masked = masked if masked != None else self.defaults.masked_response
		return wssMessageSender(self, masked, msg_type)




class wssFrameMask:
	"""
	WSS frame mask.
	Simplified XOR interface.
	- session:wss_session
	    Parent session.
	- mask_bytes:bytes
	    Mask bytes to XOR with.
	"""
	def __init__(self, session, mask_bytes):
		self.session = session
		self.xor = self.session.apply_mask
		# self._bytes_original = mask_bytes
		self.bytes_static = mask_bytes
		self.bytes = self.session.collections.deque(list(mask_bytes))

	def apply(self, data):
		"""
		Apply mask to data.
		- data:bytes
			Bytes to XOR.
		"""
		xored = self.xor(data, bytes(self.bytes))
		self.bytes.rotate(len(data))
		return xored




class wssFrameFlags:
	# 4 flag bits
	fin = None
	rsv1 = None
	rsv2 = None
	rsv3 = None

	# whether payload is masked
	masked = True

	# remaining 4 bits
	# opcode
	opcode = None




class wssOpcodes:
	continuation = 0x0
	is_text =      0x1
	is_binary =    0x2
	sig_close =    0x8
	ping =         0x9
	pong =         0xA



class wssFrame:
	"""
	Construct a WSS frame info either from bytes or a dict of params.

	- session:wss_session
	    Parent session
	- construct_info:dict
		This data should represent all the info needed to
		construct a payload header.
		This can only be used when creating a new frame.
		NOT evaluating an incoming frame
			{
				'flags': {
					'fin':    bool,
					'rsv1':   bool,
					'rsv2':   bool,
					'rsv3':   bool,
					'opcode': 0b00001111,
					'masked': bool,
				},
				'payload_size': int,
			}
	"""
	def __init__(self, session, construct_info=None):
		self.session = session

		self.flags = wssFrameFlags()

		self.length = None
		self.mask = None

		if isinstance(construct_info, dict):
			self.flags.fin =    construct_info['flags']['fin']
			self.flags.rsv1 =   construct_info['flags']['rsv1']
			self.flags.rsv2 =   construct_info['flags']['rsv2']
			self.flags.rsv3 =   construct_info['flags']['rsv3']
			self.flags.opcode = construct_info['flags']['opcode']
			self.flags.masked = construct_info['flags']['masked']
			self.length =       construct_info['payload_size']

			if self.flags.masked:
				self.create_mask()


	def eval_flags(self, data):
		"""
		Evaluate flags either from a dictionary or bytes
		- data:bytes|dict.
			First byte (8 bits) of the frame.
			OR
			dict:
			{
				'fin':    bool,
				'rsv1':   bool,
				'rsv2':   bool,
				'rsv3':   bool,
				'opcode': 0b00001111,
				'masked': bool
			}
		"""
		# if isinstance(data, bytes):
		if type(data) in (bytes, int):
			bits = data
			if isinstance(data, bytes):
				# unpack bytes
				struct = self.session.struct
				bits = struct.unpack('!B', data)

			# extract data
			self.flags.fin =    True if bits & 0b10000000 else False
			self.flags.rsv1 =   True if bits & 0b01000000 else False
			self.flags.rsv2 =   True if bits & 0b00100000 else False
			self.flags.rsv3 =   True if bits & 0b00010000 else False
			self.flags.opcode =         bits & 0b00001111

			return


		if isinstance(data, dict):
			self.flags.fin =    data['fin']
			self.flags.rsv1 =   data['rsv1']
			self.flags.rsv2 =   data['rsv2']
			self.flags.rsv3 =   data['rsv3']
			self.flags.opcode = data['opcode']
			self.flags.masked = data['masked']


	def eval_mask_state(self, data):
		"""
		Determine whether mask is set to True
		from the second byte of the payload.
		- bytes:bytes|int
			Second byte of the frame header
		"""
		if isinstance(data, bytes):
			data = self.session.struct.unpack('!B', data)
		self.flags.masked = True if data & 0b10000000 else False


	def eval_length(self, data, strip_mask=True):
		"""
		Evaluate payload length from received bytes.
		- data:bytes|int
			- bytes: Evaluate int FROM bytes
					 Unpacking size is determined automatically
					 from the amount of bytes passed.
			- int: Evaluate int TO bytes
		- strip_mask:bool
			Strip first bit of the data.
			Only works if data is isntance of int
		"""
		if isinstance(data, bytes):
			struct = self.session.struct

			if len(data) == 1:
				data = struct.unpack('!B', data)[0]
				if strip_mask:
					data = data & 0b01111111
				self.length = data
			if len(data) == 2:
				self.length = struct.unpack('!H', data)[0]
			if len(data) == 3:
				self.length = struct.unpack('!Q', data)[0]

			return self.length

		if isinstance(data, int):
			if strip_mask:
				data = data & 0b01111111
			self.length = data


	def create_mask(self, data=None):
		"""
		Create mask from bytes.
		- data:bytes=None
			Mask bytes.
			If left None - generate new mask.
		"""
		if not data:
			data = self.session.secrets.token_bytes(4)
		self.mask = wssFrameMask(self.session, data)


	def construct_header(self):
		"""
		Construct frame header bytes from the info that was written down. 
		"""
		length = self.length
		struct = self.session.struct

		# First byte
		head1 = (
			# FIN bit. 1 = fin, 0 = continue
			(0b10000000 if self.flags.fin else 0)
			# Useless shit (poor documentation + not supported by browsers)
			| (0b01000000 if self.flags.rsv1 else 0)
			| (0b00100000 if self.flags.rsv2 else 0)
			| (0b00010000 if self.flags.rsv3 else 0)
			# The opcode of the first frame in a sequence of fragmented frames
			# has to specify the type of the sequence (bytes/text/ping)
			# whereas all the following fragmented frames should have an opcode of 0x0
			# (finaly frame is marked with the fin bit)
			| self.flags.opcode
		)

		# Second byte
		head2 = 0b10000000 if self.flags.masked else 0b00000000
		if length < 126:
			header = struct.pack('!BB', head1, head2 | length)
		elif length < 65536:
			header = struct.pack('!BBH', head1, head2 | 126, length)
		else:
			header = struct.pack('!BBQ', head1, head2 | 127, length)

		if self.flags.masked:
			return (header + self.mask.bytes_static)
		else:
			return header



class wssMessageReceiver:
	"""
	Receive a WSS message.
	- session:wss_session
	"""
	def __init__(self, session, maxsize=None, chunksize=None):
		self.session = session
		self.connection = self.session.connection

		self.maxsize = maxsize
		self.chunksize = chunksize

		self.message_type = 0x2


	def receive_frame(self):
		# First, initialize new frame
		wframe = wssFrame(self.session)

		# First - await 2 header essential header bytes
		hbyte1, hbyte2 = self.session.aligned_receive(2)

		# treat first byte (flags)
		wframe.eval_flags(hbyte1)
		# treat second byte (mask state)
		wframe.eval_mask_state(hbyte2)
		# payload len
		wframe.eval_length(hbyte2)
		if wframe.length == 126:
			wframe.eval_length(self.session.aligned_receive(2))
		elif wframe.length == 127:
			wframe.eval_length(self.session.aligned_receive(8))
		# masking, if any
		if wframe.flags.masked:
			wframe.create_mask(self.session.aligned_receive(4))

		# important todo: simply split this function into "receive_header" "receive_payload"
		yield wframe

		quota = wframe.length
		# receive actual payload of the frame
		while True:
			if quota <= 0:
				break

			# why not use aligned receive?
			data = self.connection.recv(clamp_num(self.chunksize, 1, quota))
			quota -= len(data)

			if wframe.flags.masked:
				yield wframe.mask.apply(data)
			else:
				yield data


	def data_stream(self):
		# Receive the first frame of the message.
		# Browsers usually split larger messages into ~512kb chunks
		frame_receiver = self.receive_frame()
		# first frame of the message also determines the type of message
		frame_info = next(frame_receiver)
		# overwrite default message type with the one provided in the frame
		self.message_type = frame_info.flags.opcode

		while True:
			for fchunk in frame_receiver:
				yield fchunk

			if frame_info.flags.fin:
				break

			frame_receiver = self.receive_frame()
			frame_info = next(frame_receiver)





class wssMessageSender:
	"""
	Stream a message to the client
	Perfect for large messages of undefined length
	- session:wss_session
	"""
	def __init__(self, session, masked:bool=False, msg_type:str='binary'):
		"""
		- session:wss_session
		- msg_type:str='binary'
		"""
		self.session = session
		self.connection = self.session.connection
		self.masked = masked
		self.first_frame = True
		self.closed = False

		self.msg_type = wssOpcodes.is_binary
		if msg_type.lower() == 'binary':
			self.msg_type = wssOpcodes.is_binary
		if msg_type.lower() == 'text':
			self.msg_type = wssOpcodes.is_text

	def __enter__(self):
		return self

	def __exit__(self, type, value, traceback):
		# Honestly, piss off
		# who tf cares?
		if not self.closed:
			frame = wssFrame(
				self.session,
				{
					'flags': {
						'fin':    True,
						'rsv1':   False,
						'rsv2':   False,
						'rsv3':   False,
						'opcode': wssOpcodes.continuation,
						'masked': self.masked,
					},
					'payload_size': 0,
				}
			)
			self.connection.sendall(frame.construct_header())

	def send_data(self, data:bytes, last:bool=False):
		"""
		Send a frame.
		- data:bytes
		"""
		if last:
			self.closed = True

		frame = wssFrame(
			self.session,
			{
				'flags': {
					'fin':    last,
					'rsv1':   False,
					'rsv2':   False,
					'rsv3':   False,
					'opcode': self.msg_type if self.first_frame else wssOpcodes.continuation,
					'masked': self.masked,
				},
				'payload_size': len(data),
			}
		)
		self.first_frame = False
		if self.masked:
			data = frame.mask.apply(data)

		# Send the header of the payload
		self.connection.sendall(frame.construct_header())

		# Send the payload itself
		self.connection.sendall(data)






