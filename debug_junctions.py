import socket
import queue
import secrets
import threading
import multiprocessing
import random
import uuid
import time

from pathlib import Path
from multiprocessing.connection import Listener as MPListener
from multiprocessing.connection import Client as MPClient
from concurrent.futures import ThreadPoolExecutor

from jag.min_wss import MinWSession
from jag.jag_util import (
	print_exception_framed,
	skt_timeout,
	terminate_skt,
	NamedPrint,
	ClassDict,
	FasterTimerSched,
)
from jag import htservice


THISDIR = Path(__file__).parent





class PYClient(NamedPrint):
	def __init__(self, junction, cl_con):
		self.junction = junction
		self.cl_con = cl_con
		self.active = True

		self.announce = {}

	def run(self):
		try:
			while True:
				msg = self.cl_con.recv()

				if msg.type == 'announce':
					self.announce[msg.data['cmd_id']] = msg.data

				if msg.type == 'fwd':
					self.junction.msg_sched.put(msg.data)
		except Exception as e:
			print_exception_framed(e)
		finally:
			self.active = False



class WSClient(NamedPrint):
	def __init__(self, junction, wskt):
		self.junction = junction
		self.wskt = wskt
		self.send_json = wskt.send_json

		self.active = True

	def fwd_announce(self):
		with skt_timeout(self.wskt.cl_con, 9.000):
			for py_cl, _ in tuple(self.junction.py_clients):
				for announce_data in tuple(py_cl.announce.values()):
					self.send_json(announce_data)

	def run(self):
		try:
			while True:
				with skt_timeout(self.wskt, 15.000):
					if self.wskt.recv_message() != b'ping':
						break
		except Exception as e:
			print_exception_framed(e)
		finally:
			self.active = False
			terminate_skt(self.wskt.cl_con)



class JunctionBridge(NamedPrint):
	def __init__(self, py_port, auth):
		self.py_port = py_port
		self.auth = auth

		self.py_con = None

	def fork(self):
		return self.__class__(self.py_port, self.auth)

	def run(self):
		if not self.py_con:
			self.py_con = MPClient(
				('127.0.0.1', self.py_port),
				authkey=self.auth,
			)
		else:
			self.nprint('Already running')

	def terminate(self):
		try:
			self.py_con.close()
		except:
			pass

	def send(self, **kwargs):
		return self.py_con.send(
			ClassDict(**kwargs)
		)

	def __enter__(self):
		self.run()
		return self

	def __exit__(self, e_type, e_val, e_trace):
		self.terminate()



class DebugJunction(NamedPrint):
	def __init__(self, ws_port=None):
		self._ws_port = ws_port or 0
		self._py_port = None

		self.py_clients = set()
		self.ws_clients = set()

		self.msg_sched = queue.Queue()

		self._auth = None

		self._py_listener = None
		self._ws_listener = None

	@property
	def auth(self):
		if self._auth:
			return self._auth

		self._auth = secrets.token_bytes()

		return self._auth


	@property
	def py_listener(self):
		if self._py_listener:
			return self._py_listener

		self._py_listener = MPListener(
			('127.0.0.1', 0),
			authkey=self.auth,
		)

		return self._py_listener

	@property
	def py_port(self):
		if self._py_port:
			return self._py_port

		self._py_port = self.py_listener.address[1]

		return self._py_port


	@property
	def ws_listener(self):
		if self._ws_listener:
			return self._ws_listener

		self._ws_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self._ws_listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

		self._ws_listener.bind(
			('', self._ws_port)
		)

		self._ws_listener.listen(69)

		return self._ws_listener

	@property
	def ws_port(self):
		if self._ws_port:
			return self._ws_port

		self._ws_port = self.ws_listener.getsockname()[1]

		return self._ws_port


	def fork(self):
		return JunctionBridge(self.py_port, self.auth)

	def py_listen(self):
		while True:
			try:
				py_cl = PYClient(
					self,
					self.py_listener.accept()
				)

				py_cl_thread = threading.Thread(
					target=py_cl.run
				)

				py_cl_thread.start()

				self.py_clients.add((
					py_cl, py_cl_thread,
				))
			except Exception as e:
				print_exception_framed(e)
				time.sleep(0.175)
				continue

	def ws_listen(self):
		while True:
			try:
				cl_con, _ = self.ws_listener.accept()

				ws_cl = WSClient(
					self,
					MinWSession(cl_con)
				)

				ws_cl_thread = threading.Thread(
					target=ws_cl.run
				)

				ws_cl_thread.start()

				ws_cl.fwd_announce()

				self.ws_clients.add((
					ws_cl, ws_cl_thread,
				))
			except Exception as e:
				print_exception_framed(e)
				time.sleep(0.075)
				continue

	def distributor(self):
		try:
			while True:
				try:
					msg = self.msg_sched.get(timeout=5)
					self.msg_sched.task_done()

					for ws_cl, _ in tuple(self.ws_clients):
						with skt_timeout(ws_cl.wskt.cl_con, 3.000):
							ws_cl.send_json(msg)
				except Exception as e:
					print_exception_framed(e)

					for cl_data in tuple(self.py_clients):
						py_cl, cl_thread = cl_data
						if not py_cl.active:
							self.py_clients.remove(cl_data)
							cl_thread.join()

					for cl_data in tuple(self.ws_clients):
						ws_cl, cl_thread = cl_data
						if not ws_cl.active:
							self.ws_clients.remove(cl_data)
							cl_thread.join()
		except Exception as e:
			self.nprintf('FATAL:')
			print_exception_framed(e)
			return

	def run(self):
		py_listen_th = threading.Thread(
			target=self.py_listen
		)

		ws_listen_th = threading.Thread(
			target=self.ws_listen
		)

		distributor_th = threading.Thread(
			target=self.distributor
		)

		py_listen_th.start()
		ws_listen_th.start()
		distributor_th.start()







def http_callback(req, reply):
	reply.send_bytes(
		(THISDIR / 'networking_debug.html')
		.read_bytes()
		.replace(b'%WS_PORT%', str(req.envdata).encode()),

		'text/html'
	)


def run_session(jag_session):
	try:
		print('Running session')
		for req, reply in jag_session.run():
			reply.headers['jag-d'] = (
				f'R:{jag_session.max_requests}/{jag_session.remaining_requests}'
			)
	except Exception as e:
		print(e)
		print_exception_framed(e, True)


def spammer(junction_bridge):
	try:
		with junction_bridge as jbridge:
			jbridge.send(
				type='announce',
				data={
					'cmd_id': 'enter',
					'data': 'AN - ' + str(uuid.uuid4()),
				},
			)
			while True:
				time.sleep(0.25 * random.random())
				jbridge.send(
					type='fwd',
					data={
						'cmd_id': 'repeat',
						'data': 'FW - ' + str(uuid.uuid4()),
					},
				)
	except Exception as e:
		print_exception_framed(e)


def main():
	debug_junction = DebugJunction()
	debug_junction.run()

	time.sleep(0.125)

	for i in range(int(10 * random.random())):
		multiprocessing.Process(
			target=spammer,
			args=(debug_junction.fork(),)
		).start()

	html_skt = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	html_skt.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
	html_skt.bind(
		('', 42612)
	)
	html_skt.listen(0)

	thread_pool = ThreadPoolExecutor(max_workers=32)

	print('HTML ready')

	alt_timers = FasterTimerSched()

	while True:
		cl_con, cl_addr = html_skt.accept()
		print('Got connection')

		thread_pool.submit(
			run_session,
			htservice.JagSession(
				cl_con,
				http_callback,

				envdata=debug_junction.ws_port,
				add_headers={
					'Fuck-Shit': 'Medic',
				},

				better_timer=alt_timers.timer,
			),
		)


if __name__ == '__main__':
	main()