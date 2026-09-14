import hashlib
import base64
import struct
import io
import collections
import json


from .jag_util import *
from .htservice import (
	JagRequest,
	JagReply,

	JagHeaders,
	JagQuery,
)



class WebSocketXORMask:
	def __init__(self, mask_bytes):
		self.bytes_static = mask_bytes
		self.bytes = collections.deque(list(mask_bytes))

	def apply(self, data):
		xored = cyclic_xor(data, bytes(self.bytes))
		self.bytes.rotate(len(data))
		return xored



class MinWSession:
	def __init__(self, cl_con, resolve_immediately=True):
		self.cl_con = cl_con

		self.hshake_resolved = False

		self.input_wss_key = None
		self.output_wss_key = None

		if resolve_immediately:
			try:
				self.resolve_handshake()
			except Exception as e:
				print_exception(e)
				raise e

	@staticmethod
	def check_handshake(state):
		def decorator(method):
			def wrap(self, *args, **kwargs):
				if self.hshake_resolved != state:
					raise AttributeError(
						'Calling this requires handshake to be '
						f"""{'NOT resolved' if not state else 'resolved'}"""
					)
				return method(self, *args, **kwargs)
			return wrap
		return decorator

	def aligned_recv(self, *args, **kwargs):
		return aligned_recv(
			self.cl_con, *args, **kwargs
		)

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
		length = None
		if isinstance(data, bytes):
			if len(data) == 1:
				data_unpack = struct.unpack('!B', data)[0]
				if strip_mask:
					data_unpack = data_unpack & 0b01111111
				length = data_unpack
			elif len(data) == 2:
				length = struct.unpack('!H', data)[0]
			else:
				length = struct.unpack('!Q', data)[0]

			return length

		if isinstance(data, int):
			if strip_mask:
				data = data & 0b01111111
			return data

	@check_handshake(False)
	def resolve_handshake(self):
		skt_rfile = self.cl_con.makefile(
			'rb', newline=b'\r\n', buffering=0
		)

		jag_req = JagRequest(
			skt_rfile,

			JagQuery.from_skt(skt_rfile),
			JagHeaders.from_skt(skt_rfile),
		)

		skt_rfile.close()

		jag_reply = JagReply(self.cl_con, JagHeaders({
			'Upgrade':    ('websocket',),
			'Connection': ('Upgrade',),

			'Sec-WebSocket-Accept': (
				base64.b64encode(
					hashlib.sha1(
						''.join((
							jag_req.headers['sec-websocket-key'],
							'258EAFA5-E914-47DA-95CA-C5AB0DC85B11',
						))
						.encode()
					)
					.digest()
				)
				.decode(),
			)
		}))

		jag_reply.rsp_code = 101
		jag_reply.send_headers()

		self.hshake_resolved = True

	@check_handshake(True)
	def recv_message(self):
		msg_buf = io.BytesIO()

		while True:
			hbytes = self.aligned_recv(2)

			hbyte1 = hbytes[0:1]
			hbyte2 = hbytes[1:2]

			# print('Received 2 header bytes:', hbytes, hbyte1, hbyte2)
			bits1 = struct.unpack('!B', hbyte1)[0]
			bits2 = struct.unpack('!B', hbyte2)[0]

			fin =    True if bits1 & 0b10000000 else False
			rsv1 =   True if bits1 & 0b01000000 else False
			rsv2 =   True if bits1 & 0b00100000 else False
			rsv3 =   True if bits1 & 0b00010000 else False
			opcode = bits1 & 0b00001111

			masked = True if bits2 & 0b10000000 else False

			frame_len = self.eval_length(hbyte2)

			if frame_len == 126:
				frame_len = self.eval_length(self.aligned_recv(2))
			elif frame_len == 127:
				frame_len = self.eval_length(self.aligned_recv(8))

			if masked:
				msg_buf.write(
					WebSocketXORMask(self.aligned_recv(4))
					.apply(self.aligned_recv(frame_len))
				)
			else:
				msg_buf.write(self.aligned_recv(frame_len))

			if fin:
				break

		return msg_buf.getvalue()

	@check_handshake(True)
	def send_message(self, data):
		data_len = len(data)
		head1 = (
			# FIN bit. 1 = fin, 0 = continue
			   0b10000000
			# Useless shit
			| (0b01000000 if False else 0)
			| (0b00100000 if False else 0)
			| (0b00010000 if False else 0)
			# The opcode of the first frame in a sequence of fragmented frames
			# has to specify the type of the sequence (bytes/text/ping)
			# whereas all the following fragmented frames should have an opcode of 0x0
			# (final frame is marked with the fin bit)
			| 0x2
		)

		head2 = 0b10000000 if False else 0b00000000

		if data_len < 126:
			header = struct.pack('!BB', head1, head2 | data_len)
		elif data_len < 65536:
			header = struct.pack('!BBH', head1, head2 | 126, data_len)
		else:
			header = struct.pack('!BBQ', head1, head2 | 127, data_len)

		self.cl_con.sendall(header)
		self.cl_con.sendall(data)

	@check_handshake(True)
	def send_json(self, data):
		self.send_message(
			json.dumps(data)
			.encode()
		)

	def terminate(self):
		terminate_skt(self.cl_con)



