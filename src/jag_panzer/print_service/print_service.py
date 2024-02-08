"""
Service responsible for printing log n stuff.

Only setup stuff or critical errors should be printed to the console.
Everything else goes to the web print.


"""
import secrets
from pathlib import Path
import socket
import json
import queue
import threading
from ..jag_internal.min_http import MinHTTP
from ..jag_internal.min_wss import MinWSession

THISDIR = Path(__file__).parent


# fuck python
# fuck it very much. Retard
def print_exception(err):
	import traceback
	try:
		print(
			'Critical Jag Internal Error:',

			''.join(
				traceback.format_exception(
					type(err),
					err,
					err.__traceback__
				)
			)
		)
	except Exception as e:
		print('Could not format exception:', e)


def wrap_exception(func):
	def _inner(*args, **kwargs):
		try:
			func(*args, **kwargs)
		except Exception as err:
			import traceback
			print(
				'Critical Jag Internal Error:',

				''.join(
					traceback.format_exception(
						type(err),
						err,
						err.__traceback__
					)
				)
			)

	return _inner


class MinHTTPRequestProcessor:
	WEBCL_ROOT_DIR = THISDIR / 'web_client'

	WEBCL_HTML_PAGE_PATH = WEBCL_ROOT_DIR / 'print_server_gui.html'

	CDN_RESOURCE_INDEX = (
		(
			'script.js',
			WEBCL_ROOT_DIR / 'script.js',
			'application/javascript',
		),
		(
			'style.css',
			WEBCL_ROOT_DIR / 'style.css',
			'text/css',
		),
		(
			'ibm_plex_bold.ttf',
			WEBCL_ROOT_DIR / 'ibm_plex_bold.ttf',
			'font/ttf',
		),
		(
			'ibm_plex_regular.ttf',
			WEBCL_ROOT_DIR / 'ibm_plex_regular.ttf',
			'font/ttf',
		),
	)

	def process_request(self, cl_request):
		for cdn_query, fpath, mime in self.CDN_RESOURCE_INDEX:
			if cdn_query in cl_request.path:
				if fpath.is_file():
					cl_request.flush_bytes(
						fpath.read_bytes(),
						mime,
					)
					return
				else:
					cl_request.deny()

		wss_url = f"""ws://127.0.0.1:{cl_request.shared_data}"""
		cl_request.flush_bytes(
			self.WEBCL_HTML_PAGE_PATH.read_bytes().replace(b'@@wss_url', wss_url.encode()),
			'text/html; charset=utf-8',
		)



class PrintPipeProtocol:
	"""
	The protocol used for the communication
	of print clients within python.
	"""
	cmd_registry = (
		'print',
		'open_group',
		'close_group',
	)

	@staticmethod
	def send_payload(
		skt_con:socket.socket,
		payload_data:dict
	):
		# Send cmd index
		skt_con.sendall(
			int.to_bytes(
				PrintPipeProtocol.cmd_registry.index(payload_data['cmd']),
				1,
				'little'
			)
		)

		# Send print column ID
		skt_con.sendall(
			int.to_bytes(payload_data['col_id'], 2, 'little')
		)

		# Send special ID
		skt_con.sendall(
			payload_data.get('special_id', '').ljust(32, '0').encode()
		)

		# Send payload length
		msg = f"""{payload_data['data']}""".encode()
		skt_con.sendall(
			int.to_bytes(len(msg), 8, 'little')
		)

		# Send the message itself
		skt_con.sendall(
			msg
		)


	@staticmethod
	def read_payload(skt_file:socket.socket.makefile):
		cmd_idx = int.from_bytes(
			skt_file.read(1),
			byteorder='little',
			signed=False
		)

		cmd = PrintPipeProtocol.cmd_registry[cmd_idx]

		col_idx = int.from_bytes(
			skt_file.read(2),
			byteorder='little',
			signed=False
		)

		cell_id = skt_file.read(32).decode()

		payload_size = int.from_bytes(
			skt_file.read(8),
			byteorder='little',
			signed=False
		)

		payload_data = skt_file.read(payload_size)

		return {
			'cmd':     cmd,
			'col_idx': col_idx,
			'cell_id': cell_id,
			'data':    payload_data
		}



class JagPrintClient:
	def __init__(
		self,
		tgt_port:int,
		cl_id:int,
		cl_name:str='',
		worker_header=None
	):
		self.cl_id = cl_id
		self.tgt_port = tgt_port
		self.cl_name = cl_name
		self.worker_header = worker_header
		self.sv_con:socket.socket | None = None

	def run(self):
		# The stuff below can be done in one line,
		# but what's the disadvantage of having an IPV6 support?
		while True:
			if self.sv_con:
				break
			try:
				for res in socket.getaddrinfo('127.0.0.1', self.tgt_port, socket.AF_UNSPEC, socket.SOCK_STREAM):
					af, socktype, proto, canonname, sa = res
					try:
						self.sv_con = socket.socket(af, socktype, proto)
					except OSError as msg:
						self.sv_con = None
						continue
					try:
						self.sv_con.connect(sa)
					except OSError as msg:
						self.sv_con.close()
						self.sv_con = None
						continue
					break
			except Exception as e:
				continue

	def print_group(self):
		return PrintGroup(self)

	def print(self, *msg, special_id=''):
		PrintPipeProtocol.send_payload(
			self.sv_con,
			{
				'cmd':        'print',
				'col_id':     self.cl_id,
				'special_id': special_id,
				'data':       ' '.join([f'{i}' for i in msg]),
			}
		)



class PrintGroup:
	def __init__(self, print_client:JagPrintClient):
		self.print_client:JagPrintClient = print_client
		self.special_id:str = secrets.token_hex(16)

	def __enter__(self):
		PrintPipeProtocol.send_payload(
			self.print_client.sv_con,
			{
				'cmd':        'open_group',
				'col_id':     self.print_client.cl_id,
				'special_id': self.special_id,

				# todo: this is unnecessary
				'data':       'Pootis',
			}
		)
		return self.group_print

	def __exit__(self, exc_type, exc_val, exc_tb):
		PrintPipeProtocol.send_payload(
			self.print_client.sv_con,
			{
				'cmd':        'close_group',
				'col_id':     self.print_client.cl_id,
				'special_id': self.special_id,

				# todo: this is unnecessary
				'data':       'Pootis',
			}
		)

	def group_print(self, *msg):
		self.print_client.print(*msg, special_id=self.special_id)



class WebclWSS:
	def __init__(self, webcl:'JagPrintServiceWebClient'):
		# Reserve a port.
		self.wss_skt = socket.socket()
		self.wss_skt.bind(
			('', 0)
		)

		# List of clients to distribute messages to
		self.cl_registry:list[MinWSession] = []

		# Reference to the Web Client class
		self.webcl = webcl

	@wrap_exception
	def serve_wss_session(self, cl_con):
		print('Opening wss session')
		wsession = MinWSession(cl_con)

		# Send print client info to the web client.
		# For now the print client is an array consisting of strings,
		# which act like some sort of a header

		# The array maps 1:1 to client index
		init_msg = {
			'cmd': 'init_info',
			'val': self.webcl.print_service.cl_header_registry,
		}

		wsession.send_message(
			json.dumps(init_msg).encode()
		)

		self.cl_registry.append(wsession)
		while True:
			try:
				msg = wsession.recv_message()
				print('Message from client:', msg)
				if not msg:
					raise ConnectionError(
						'The client has disconnected'
					)
			except ConnectionError as e:
				# print_exception(e)
				print('The client has aborted the connection')
				break

		print('Deleting session from registry')
		del self.cl_registry[self.cl_registry.index(wsession)]

	@wrap_exception
	def	run_wss(self):
		self.wss_skt.listen(0)

		while True:
			try:
				cl_con, addr = self.wss_skt.accept()
				# Create a WSS session
				threading.Thread(
					target=self.serve_wss_session,
					args=(cl_con,)
				).start()
			except ConnectionError as e:
				print_exception(e)
				continue

	@wrap_exception
	def broadcast(self):
		while True:
			self.webcl.wss_broadcast_queue_event.wait()
			self.webcl.wss_broadcast_queue_event.clear()

			with self.webcl.wss_broadcast_queue_lock:
				while not self.webcl.wss_broadcast_queue.empty():
					msg = self.webcl.wss_broadcast_queue.get()
					for wss_cl in self.cl_registry:
						try:
							wss_cl.send_message(msg)
						except ConnectionError as e:
							print(
								'WSS Session ended before the message could be delivered'
							)
							continue





class JagPrintServiceWebClient:
	def __init__(self, print_service:'JagPrintService'):
		# todo: is this retarded in terms of
		# how things are properly done in python ?
		self.wss_broadcast_queue:queue.Queue | None = None
		self.wss_broadcast_queue_lock:threading.Lock | None = None
		self.wss_broadcast_queue_event:threading.Event | None = None

		# Reference to the root print service
		self.print_service = print_service

		# Create WSS server, but don't listen yet
		# (reserving a port)
		self.wss = WebclWSS(self)

		# Create the HTTP server, but don't listen yet
		# (reserving a port)
		self.http_request_processor = MinHTTPRequestProcessor()
		self.min_http = MinHTTP(
			self.http_request_processor.process_request,
			self.wss.wss_skt.getsockname()[1],
		)

	@wrap_exception
	def run_webcl(self):
		self.wss_broadcast_queue = queue.Queue()
		self.wss_broadcast_queue_lock = threading.Lock()
		self.wss_broadcast_queue_event = threading.Event()

		# Run wss
		threading.Thread(target=self.wss.run_wss).start()
		# Run minhttp
		threading.Thread(target=self.min_http.serve, args=(8091,)).start()
		# Broadcast queue
		threading.Thread(target=self.wss.broadcast).start()



class JagPrintService:
	def __init__(self):
		# Reserve socket to listen to
		# todo: are there any useful parameters to pass to socket.socket() ?
		self.skt = socket.socket()
		self.skt.bind(
			('127.0.0.1', 0)
		)

		self.cl_header_registry = []

		# Create the webclient, therefore reserving a socket for it
		self.web_client = JagPrintServiceWebClient(self)

	def create_print_column(
		self,
		worker_header=None
	) -> JagPrintClient:

		self.cl_header_registry.append(worker_header)

		return JagPrintClient(
			self.skt.getsockname()[1],
			# Fun fact: Every single solution on the internet is
			# utterly fucking retarded. Those, who suggested
			# to do what is done below, WITHOUT max()
			# are not even stupid, but have an empty void of negative size
			# instead of their brains.
			max(len(self.cl_header_registry) - 1, 0),
			worker_header,
		)

	def start(self):
		self.web_client.run_webcl()
		threading.Thread(target=self.listener).start()

	def process_pipe_payload(self, skt_file):
		msg_data = PrintPipeProtocol.read_payload(skt_file)

		with self.web_client.wss_broadcast_queue_lock:
			msg = {
				'cmd': msg_data['cmd'],
				'val': {
					'col_idx':    msg_data['col_idx'],
					'special_id': msg_data['cell_id'],
					'self_name':  None,
					'data':       msg_data['data'].decode(),
				}
			}

			self.web_client.wss_broadcast_queue.put(
				json.dumps(msg).encode()
			)

			self.web_client.wss_broadcast_queue_event.set()

	@wrap_exception
	def print_session(self, cl_con):
		print('Entering print session')
		# Create file to read from
		skt_file = cl_con.makefile('rb')
		while True:
			try:
				self.process_pipe_payload(skt_file)
			except ConnectionAbortedError as e:
				print(
					'Critical error: a print pipe has broken. You cannot comprehend how bad this is...'
				)
				print_exception(e)
				break
			except Exception as e:
				continue


	@wrap_exception
	def listener(self):
		self.skt.listen(0)
		while True:
			cl_con, address = self.skt.accept()
			threading.Thread(
				target=self.print_session,
				args=(cl_con,)
			).start()









