import socket
import queue
import secrets
import threading
import multiprocessing
import random
import uuid
import time
import sys

from pathlib import Path
from multiprocessing.connection import Listener as MPListener
from multiprocessing.connection import Client as MPClient
from concurrent.futures import ThreadPoolExecutor

from .jag_util import (
	print_exception_framed,
	skt_timeout,
	terminate_skt,
	NamedPrint,
	ClassDict,
	FasterTimerSched,
)


THISDIR = Path(__file__).parent






class WSClient(NamedPrint):
	def __init__(self, junction, wskt):
		self.junction = junction
		self.wskt = wskt
		self.send_json = wskt.send_json

		self.active = True

	def fwd_announce(self):
		with skt_timeout(self.wskt.cl_con, 9.000):
			for announce_data in tuple(self.junction.announce_data.values()):
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
			sys.exit()


class WSDebug(NamedPrint):
	def __init__(self, page_port, msg_sched):
		self.page_port = page_port
		self.msg_sched = msg_sched
		self.ws_clients = set()
		self.announce_data = {}

		self._ws_listener = None

	@staticmethod
	def announce(id, data):
		return ClassDict(
			type='announce',
			id=id,
			data=data,
		)

	@staticmethod
	def denounce(id, data):
		return ClassDict(
			type='denounce',
			id=id,
			data=data,
		)

	@staticmethod
	def fwd(data):
		return ClassDict(
			type='fwd',
			data=data,
		)

	@property
	def ws_listener(self):
		if self._ws_listener:
			return self._ws_listener

		self._ws_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self._ws_listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

		self._ws_listener.bind(
			('', 0)
		)

		self._ws_listener.listen(69)

		return self._ws_listener

	def distributor(self):
		try:
			while True:
				try:
					msg = self.msg_sched.get(timeout=5)
					# self.msg_sched.task_done()

					if msg.type == 'announce':
						self.announce_data[msg.id] = msg.data
					if msg.type == 'denounce':
						for key in tuple(self.announce_data.keys()):
							if key.startswith(msg.id):
								try:
									del self.announce_data[key]
								except:
									pass

					for ws_cl, _ in tuple(self.ws_clients):
						with skt_timeout(ws_cl.wskt.cl_con, 3.000):
							ws_cl.send_json(msg.data)
				except queue.Empty:
					continue
				except Exception as e:
					print_exception_framed(e)

					for cl_data in tuple(self.ws_clients):
						ws_cl, cl_thread = cl_data
						if not ws_cl.active:
							self.ws_clients.remove(cl_data)
							cl_thread.join()
		except Exception as e:
			self.nprintf('FATAL:')
			print_exception_framed(e)
			return

	def ws_listen(self):
		# important todo: this is fucking stupid
		from .min_wss import MinWSession

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

	def serve_page(self):
		# important todo: this is fucking stupid
		from .htservice import JagSession

		# Threads
		thread_pool = ThreadPoolExecutor(max_workers=16)

		# Listen socket
		skt = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		skt.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		skt.bind(
			('', self.page_port)
		)
		skt.listen(69)

		# Better timers
		alt_timers = FasterTimerSched()

		# Basic callback
		def callback(req, reply):
			reply.send_bytes(
				Path('E:/!webdesign/jag/tests/networking_debug.html')
				.read_bytes()
				.replace(
					b'%WS_PORT%',
					req.envdata,
				),

				'text/html',
			)

		ws_port = str(self.ws_listener.getsockname()[1]).encode()

		# Serve HTML page
		while True:
			try:
				cl_con, cl_addr = skt.accept()

				thread_pool.submit(
					JagSession(
						cl_con,
						callback,

						envdata=ws_port,

						better_timer=alt_timers.timer,
					)
					.run_auto
				)
			except Exception as e:
				print_exception_framed(e)

	def run(self):
		ws_listen_th = threading.Thread(
			target=self.ws_listen
		)

		distributor_th = threading.Thread(
			target=self.distributor
		)

		serve_page_th = threading.Thread(
			target=self.serve_page
		)

		ws_listen_th.start()
		distributor_th.start()
		serve_page_th.start()

		self.nprint('Running debug junction')




