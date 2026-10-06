import socket
import time
import sys
import os
import builtins
import uuid
import multiprocessing


from concurrent.futures import ThreadPoolExecutor


from .jag_h1 import *
from .jag_util import *
from .mp_debug import WSDebug




REUSEPORT_AVAILABLE = hasattr(socket, 'SO_REUSEPORT')


dbg_print = print


def place_kcas(sched):
	real_print = print

	def impostorous_print(*args, **kwargs):
		try:
			sep = str(kwargs.get('sep', ' '))
			end = str(kwargs.get('end', '\n'))

			sched.put(
				# '[KCAS]' + sep.join(str(arg) for arg in args)
				sep.join(str(arg) for arg in args)
				# '[KCAS]' + sep.join(str(arg) for arg in args) + end
				# '[KCAS]' + '\n' + sep.join(str(arg) for arg in args) + end
			)
		except Exception as e:
			pass
			# dbg_print(
			# 	'LOGGER FATAL:',
			# 	str_exception(e)
			# )

	builtins.print = impostorous_print






class WSDebugMessagingProxy:
	def __init__(self, ws_debug):
		self.ws_debug = ws_debug

	def announce(self, *args, **kwargs):
		if self.ws_debug:
			return self.ws_debug.put(
				WSDebug.announce(*args, **kwargs)
			)

	def denounce(self, *args, **kwargs):
		if self.ws_debug:
			return self.ws_debug.put(
				WSDebug.denounce(*args, **kwargs)
			)

	def fwd(self, *args, **kwargs):
		if self.ws_debug:
			return self.ws_debug.put(
				WSDebug.fwd(*args, **kwargs)
			)



class WSDebugMessaging:
	@property
	def ws_dbg_msg(self):
		return WSDebugMessagingProxy(
			getattr(self, 'ws_debug', None)
		)



# No, sockets absolutely should NOT be placed in a fucking sched or anything,
# because that's basically a fucking limbo, which is unacceptable.
class MPSocketAcceptorThreadPool(LifeRemaining, NamedPrint, WSDebugMessaging):
	DEFAULT_THREAD_AMOUNT = 16
	DEFAULT_MAX_SESSIONS =  50

	# DEFAULT_MAX_LIFE_S =       169.000
	DEFAULT_MAX_LIFE_S =       JagSession.DEFAULT_LIFE_DUR_S * 2
	DEFAULT_FINISH_TIMEOUT_S = DEFAULT_MAX_LIFE_S * 0.5

	DEFAULT_USE_BETTER_TIMERS = True


	def __init__(self,
		# mp pipe to receive socket connections from
		pipe,

		# Part of params for JagSession, but none of this
		# can exist without a callback, so it's mandatory
		callback,

		# Max. amount of threads in thread pool
		thread_amount=None,
		# How many sessions can pass through this pool before it stops,
		# finishes remaining tasks and collapses
		max_sessions=None,
		# Max. life of this pool in seconds.
		# Once this is reached - the pool stops accepting connections
		# and waits for existing connections to finish
		max_life_s=None,
		# When the timeout described above is reached - existing sessions
		# have this many seconds to finish executing before this process
		# and therefore their connection is force terminated
		finish_timeout_s=None,

		# Whether to substitute threading.Timer with jag's shit,
		# which is SUPPOSEDLY better & faster
		user_better_timers=None,

		# KCAS
		kcas=None,
		# WS debug junction
		ws_debug=None,
		# For debug
		acceptor_id=None,
		pool_id=None,

		# Params for JagSession
		session_args=None,
		session_kwargs=None,
	):
		super().__init__(
			max_life_s or self.DEFAULT_MAX_LIFE_S
		)

		self.acceptor_id = acceptor_id or '--ACCEPTOR_ID_UNKNOWN--'
		self.pool_id = pool_id or '--POOL_ID_UNKNOWN --'

		self.pipe = pipe
		self.callback = callback

		self.kcas = kcas
		self.ws_debug = ws_debug

		self.thread_amount =    thread_amount    or self.DEFAULT_THREAD_AMOUNT
		self.max_sessions =     max_sessions     or self.DEFAULT_MAX_SESSIONS
		self.finish_timeout_s = finish_timeout_s or self.DEFAULT_FINISH_TIMEOUT_S

		self.session_args = tuple(session_args or ())
		self.session_kwargs = dict(session_kwargs or {})

		self.session_counter = 0

		if bool_param(user_better_timers, self.DEFAULT_USE_BETTER_TIMERS):
			self.timer_sched = FasterTimerSched()
			self.better_timer = self.timer_sched.timer
			self.session_kwargs['better_timer'] = self.better_timer
		else:
			self.timer_sched = None
			self.better_timer = None

	@staticmethod
	def os_exit():
		os._exit(1)

	@classmethod
	def mp_spawn(cls, kcas, *args, **kwargs):
		try:
			if kcas:
				place_kcas(kcas)

			thread_pool = cls(*args, **kwargs)

			acceptor_id = kwargs.get('acceptor_id')
			pool_id =     kwargs.get('pool_id')
			cls.nprint('Spawned pool', f'{acceptor_id}.{pool_id}')
			thread_pool.ws_dbg_msg.announce(pool_id, {
				'cmd_id': 'thread_pool.create',
				'data': {
					'acceptor_id': acceptor_id,
					'pool_id': pool_id,
				}
			})

			thread_pool.run()
		except Exception as e:
			cls.nprint('FATAL:', e)
			print_exception_framed(e)
		finally:
			cls.os_exit()

	def timeout_callback(self):
		self.nprintf('Timeout triggered')
		try:
			self.ws_dbg_msg.announce(f'{self.pool_id}.status', {
				'cmd_id': 'thread_pool.shutdown',
				'data': {
					'acceptor_id': self.acceptor_id,
					'pool_id': self.pool_id,
					'reason': 'timeout',
				},
			})
		except Exception as e:
			print_exception_framed(e)

		time.sleep(self.finish_timeout_s)
		self.os_exit()

	@contextlib.contextmanager
	def timeout(self, timeout_override=None):
		timer = (self.better_timer or threading.Timer)(
			timeout_override or self.life_remaining,
			self.timeout_callback,
		)

		try:
			timer.start()
			yield timer
		finally:
			timer.cancel()

	@LifeRemaining.clock_start
	def run(self):
		# Create pool for JagSession instances
		thread_pool = ThreadPoolExecutor(
			max_workers=self.thread_amount
		)

		while (self.session_counter < self.max_sessions):
			# First message is always a probe
			# Basically, LIFE timeout can ONLY interrupt the probe message
			# to ensure that no socket gets denied
			with self.timeout():
				self.nprintf(
					'Received probe:',
					self.pipe.recv(),
				)

			self.ws_dbg_msg.fwd({
				'cmd_id': 'thread_pool.probe',
				'data': {
					'acceptor_id': self.acceptor_id,
					'pool_id': self.pool_id,
				},
			})

			# Everything inside this should happen within milliseconds
			with self.timeout(5.000):
				# Whether next message is expected to be a socket
				skt_expected = (
					# Whether max session amount has been reached
					(self.session_counter < self.max_sessions)
					# Whether max life duration has been reached
					# (with a tiny threshold of 17% of max. life duration)
					and (self.life_remaining > (self.lfr_dur_s * 0.17))
				)

				# Reply whether a socket can be accepted
				self.pipe.send(skt_expected)

				self.nprintf('Replied with:', skt_expected)

				if not skt_expected:
					break

				# This now has to be a valid socket connection
				if not (skt_con := self.pipe.recv()):
					raise ValueError(
						'FATAL: Socket connection expected, '
						f'but got {skt_con}'
					)

			self.nprint('Received connection:', skt_con)
			self.ws_dbg_msg.fwd({
				'cmd_id': 'thread_pool.accept_connection',
				'data': {
					'acceptor_id': self.acceptor_id,
					'pool_id': self.pool_id,
				},
			})

			# Run the session
			thread_pool.submit(
				JagSession(
					skt_con,
					self.callback,

					*self.session_args,
					**self.session_kwargs,
				)
				.run_auto
			)

			self.ws_dbg_msg.announce(f'{self.pool_id}.session_count', {
				'cmd_id': 'thread_pool.update_session_count',
				'data': {
					'acceptor_id': self.acceptor_id,
					'pool_id': self.pool_id,
					'counter': self.session_counter,
				},
			})

			# Signal that everything SEEMS to have gone ok
			self.pipe.send(True)

			self.session_counter += 1

		try:
			self.pipe.close()
		except Exception as e:
			print_exception_framed(e)
		finally:
			self.nprint('Max sessions reached. Starting termination countdown')
			self.ws_dbg_msg.announce(f'{self.pool_id}.status', {
				'cmd_id': 'thread_pool.shutdown',
				'data': {
					'acceptor_id': self.acceptor_id,
					'pool_id': self.pool_id,
					'reason': 'max_sessions',
				},
			})
			with self.timeout(self.finish_timeout_s):
				thread_pool.shutdown(wait=True)
				self.ws_dbg_msg.announce(f'{self.pool_id}.status', {
					'cmd_id': 'thread_pool.shutdown',
					'data': {
						'acceptor_id': self.acceptor_id,
						'pool_id': self.pool_id,
						'reason': 'all_done',
					},
				})
				# time.sleep(2)



# Persistent worker
class MPSocketAcceptor(NamedPrint, WSDebugMessaging):
	DEFAULT_POOL_AMOUNT = 3
	DEFAULT_SKT_CON_HARD_LIMIT = 4096

	def __init__(self,
		# EITHER port to listen on
		# (useful on Linux where ports can somehow be reused)
		# OR a socket object
		# (Windows can't reuse ports)
		skt_data,

		# Callback function to call on each HTTP request
		callback,

		# How many thread pools to keep
		pool_amount=None,

		# Kcas prints
		kcas=None,
		# WS live debug
		ws_debug=None,
		# Debug-related
		acceptor_id=None,

		# Args for MPSocketAcceptorThreadPool
		pool_args=None,
		pool_kwargs=None,

		# Args for JagSession
		session_args=None,
		session_kwargs=None,
	):
		# Can't be port 0
		# Can't be None
		# HAS TO BE a non-zero number or otherwise valid object
		if not skt_data:
			msg = (
				f'FATAL: invalid skt_data ({skt_data})'
			)
			self.nprint(msg)
			raise ValueError(msg)

		# Reuseport is only available on Linux
		if isinstance(skt_data, tuple) and not REUSEPORT_AVAILABLE:
			msg = (
				f'FATAL: skt_data ({skt_data}) seems to be a port, '
				'but socket.SO_REUSEPORT is NOT available'
			)
			self.nprint(msg)
			raise ValueError(msg)

		self.acceptor_id = acceptor_id or '--ACCEPTOR_ID_UNKNOWN--'

		self.skt_data = skt_data
		self.callback = callback

		self.kcas = kcas
		self.ws_debug = ws_debug

		self.pool_amount = pool_amount or self.DEFAULT_POOL_AMOUNT

		self.pool_args = (callback, *tuple(pool_args or ()))
		self.pool_kwargs = {
			**(pool_kwargs or {}),
			'session_args':   tuple(session_args or ()),
			'session_kwargs': dict(session_kwargs or {}),
			'ws_debug':       ws_debug,
			'acceptor_id':    self.acceptor_id,
		}

		self.pool_array = set()

		self._listen_skt = None

		self.th_lock = threading.Lock()

	@staticmethod
	def os_exit():
		os._exit(1)

	@classmethod
	def mp_spawn(cls, kcas, *args, **kwargs):
		try:
			if kcas:
				place_kcas(kcas)
				kwargs['kcas'] = kcas

			acceptor = cls(*args, **kwargs)

			cls.nprint('Spawned acceptor', acceptor.acceptor_id)
			acceptor.ws_dbg_msg.announce(acceptor.acceptor_id, {
				'cmd_id': 'acceptor.create',
				'data': acceptor.acceptor_id,
			})

			acceptor.run()
		except Exception as e:
			print_exception_framed(e)
			try:
				acceptor.terminate()
			except:
				pass
		finally:
			cls.os_exit()

	@property
	def listen_skt(self):
		if self._listen_skt != None:
			return self._listen_skt

		if isinstance(self.skt_data, tuple) and REUSEPORT_AVAILABLE:
			self.nprint('REUSEPORT')
			self._listen_skt = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

			self._listen_skt.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
			self._listen_skt.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)

			self._listen_skt.bind(self.skt_data)

			self._listen_skt.listen(
				self.DEFAULT_SKT_CON_HARD_LIMIT
			)
		else:
			self.nprint('SOCKET AS IS')
			self._listen_skt = self.skt_data

		return self._listen_skt

	def terminate(self):
		try:
			for pool_proc, _, _ in tuple(self.pool_array):
				try:
					pool_proc.kill()
				except Exception as e:
					print_exception_framed(e)
		except Exception as e:
			print_exception_framed(e)
		finally:
			self.os_exit()

	def joiner(self):
		while True:
			try:
				time.sleep(3.000)
				for pool_data in tuple(self.pool_array):
					pool_proc, _, _ = pool_data
					if not pool_proc.is_alive():
						self.remove_pool(pool_data)
			except Exception as e:
				print_exception_framed(e)

	def spawn_pool(self):
		pool_id = str(uuid.uuid4())

		pool_pipe_a, pool_pipe_b = multiprocessing.Pipe()
		pool_proc = multiprocessing.Process(
			target=MPSocketAcceptorThreadPool.mp_spawn,

			args=(
				self.kcas,
				pool_pipe_a,
				*self.pool_args
			),

			kwargs={
				**self.pool_kwargs,
				'pool_id': pool_id,
			},
		)
		pool_proc.start()

		pool_data = (pool_proc, pool_pipe_b, pool_id)

		self.pool_array.add(pool_data)

		return pool_data

	def remove_pool(self, pool_data):
		with self.th_lock:
			pool_proc, pool_pipe, pool_id = pool_data
			try:
				pool_proc.kill()
				pool_proc.join()
				self.pool_array.remove(pool_data)
				if self.ws_debug:
					self.ws_debug.put(WSDebug.denounce(pool_id, {
						'cmd_id': 'thread_pool.remove',
						'data': {
							'acceptor_id': self.acceptor_id,
							'pool_id': pool_id,
						},
					}))
			except Exception as e:
				print_exception_framed(e)

	def find_free_pool(self):
		tgt_pool = None
		for pool_data in tuple(self.pool_array):
			pool_proc, pool_pipe, _ = pool_data
			try:
				if not pool_proc.is_alive():
					self.nprintf('Found dead pool. Removing', pool_data)
					self.remove_pool(pool_data)
					continue

				if not tgt_pool:
					# Send probe
					pool_pipe.send(None)
					# If reply ok - the pool is waiting for a socket
					if pool_pipe.recv():
						tgt_pool = pool_data
			except Exception as e:
				print_exception_framed(e)

		return tgt_pool

	def assign_con(self, cl_con, pool_data):
		pool_proc, pool_pipe, _ = pool_data
		try:
			pool_pipe.send(cl_con)
			if pool_pipe.recv():
				# cl_con.close()
				return True
			else:
				self.remove_pool(pool_data)
		except Exception as e:
			self.nprintf('Failed to assign client connection to a pool:')
			print_exception_framed(e)
			self.remove_pool(pool_data)

		return False

	def run(self):
		threading.Thread(target=self.joiner).start()

		while True:
			cl_con, cl_addr = self.listen_skt.accept()
			self.nprint('Accepted connection:', cl_con, cl_addr)

			self.ws_dbg_msg.fwd({
				'cmd_id': 'acceptor.got_connection',
				'data': self.acceptor_id,
			})

			while True:
				# See if a pool is available
				if (pool_data := self.find_free_pool()):
					self.nprintf('Found free pool after waiting')
					if self.assign_con(cl_con, pool_data):
						self.ws_dbg_msg.fwd({
							'cmd_id': 'acceptor.working',
							'data': self.acceptor_id,
						})
						break

				# Check if a new pool can be created. If not - wait
				if len(self.pool_array) < self.pool_amount:
					for _ in range(4):
						self.spawn_pool()
						if not (pool_data := self.find_free_pool()):
							self.nprintf(
								'WARNING: Pool created, but not '
								'immediately available.'
							)
							continue

						if self.assign_con(cl_con, pool_data):
							self.nprintf(
								'Created a new pool and assigned '
								'a connection to it'
							)

							self.ws_dbg_msg.fwd({
								'cmd_id': 'acceptor.working',
								'data': self.acceptor_id,
							})
							break
					else:
						raise ValueError(
							'FATAL: Too many failed pool creation attempts'
						)

					break

				self.nprintf('Waiting for a free spot')
				self.ws_dbg_msg.fwd({
					'cmd_id': 'acceptor.waiting',
					'data': self.acceptor_id,
				})
				time.sleep(0.250)



# Multiprocessed complex tomfoolery
class MPNetworking(NamedPrint, WSDebugMessaging):
	DEFAULT_ACCEPTOR_AMOUNT = 3

	# Not a parameter, because it's too low-level
	ACCEPTOR_MGE_STATUS_CHECK_INTERVAL_S = 3.000

	# Этот скрипт КСАСа просит
	DEFAULT_KCAS_PLACEMENT_ENABLED = True

	DEFAULT_WS_DEBUG_ENABLED = False
	DEFAULT_WS_DEBUG_PORT = 59173

	def __init__(self,
		# Address to bind to
		bind_addr,

		# HTTP request callback function
		callback,

		*args,

		# How many persistent connection +acceptors to keep
		acceptor_amount=None,

		# Whether to make it so that all print statements from all the
		# descendant processes get siphoned back into main process
		# and scheduled for sequential execution.
		# Prevents multi-line print statements from overlapping.
		kcas_enabled=None,

		# Server load live monitoring with websockets
		ws_debug_enabled=None,
		ws_debug_port=None,

		**kwargs,
	):
		self.bind_addr = bind_addr
		self.callback = callback

		self.acceptor_amount = acceptor_amount or self.DEFAULT_ACCEPTOR_AMOUNT

		self.kcas_enabled = bool_param(
			kcas_enabled,
			self.DEFAULT_KCAS_PLACEMENT_ENABLED,
		)

		self.ws_debug_enabled = bool_param(
			ws_debug_enabled,
			self.DEFAULT_WS_DEBUG_ENABLED,
		)
		self.ws_debug_port = ws_debug_port or self.DEFAULT_WS_DEBUG_PORT

		self.acceptor_args = args
		self.acceptor_kwargs = kwargs

		self.acceptor_pool = set()
		self.mp_mng = None
		self.kcas = None
		self.ws_debug = None
		self.skt_data = None

	@staticmethod
	def logs_printer(sched):
		while True:
			try:
				while True:
					dbg_print(
						sched.get()
					)
			except Exception as e:
				dbg_print('KCAS FATAL:', str_exception(e))
				time.sleep(0.1)

	# Create an arduous socket with no SO_REUSEPORT
	@staticmethod
	def dreary_skt(addr):
		skt = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		skt.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		skt.bind(addr)
		skt.listen(
			MPSocketAcceptor.DEFAULT_SKT_CON_HARD_LIMIT * 2
		)

		return skt

	def launch_kcas(self):
		self.kcas = self.mp_mng.Queue()
		printer_th = threading.Thread(
			target=self.logs_printer,
			args=(self.kcas,),
			daemon=True
		)
		printer_th.start()
		self.nprintf('Started logs printer thread')
		place_kcas(self.kcas)
		self.nprintf('Placed KCAS in main process')

	def launch_ws_debug(self):
		self.ws_debug = self.mp_mng.Queue()
		WSDebug(self.ws_debug_port, self.ws_debug).run()

	def create_acceptor(self):
		acceptor_id = str(uuid.uuid4())
		acceptor_proc = multiprocessing.Process(
			target=MPSocketAcceptor.mp_spawn,

			args=(
				self.kcas,
				self.skt_data,
				self.callback,
				*self.acceptor_args
			),

			kwargs={
				**self.acceptor_kwargs,
				'acceptor_id': acceptor_id,
				'ws_debug': self.ws_debug,
			},
		)

		acceptor_data = (acceptor_proc, acceptor_id)
		self.acceptor_pool.add(acceptor_data)

		acceptor_proc.start()

		return acceptor_data

	def remove_acceptor(self, acceptor_data):
		acceptor_proc, acceptor_id = acceptor_data

		acceptor_proc.kill()
		acceptor_proc.join()
		self.acceptor_pool.remove(acceptor_data)
		self.nprintf('Removed acceptor', acceptor_id, acceptor_proc)

		self.ws_dbg_msg.denounce(acceptor_id, {
			'cmd_id': 'acceptor.remove',
			'data': acceptor_id,
		})

	def run(self):
		with multiprocessing.Manager() as mp_mng:
			self.mp_mng = mp_mng

			# Launch a bunch of shit
			if self.kcas_enabled:
				self.launch_kcas()

			if self.ws_debug_enabled:
				self.launch_ws_debug()


			# Create socket data
			if REUSEPORT_AVAILABLE:
				self.skt_data = self.bind_addr
			else:
				self.skt_data = self.dreary_skt(self.bind_addr)


			# Maintain acceptors
			while True:
				for acceptor_data in tuple(self.acceptor_pool):
					acceptor_proc, acceptor_id = acceptor_data
					if acceptor_proc.is_alive():
						continue

					self.nprintf(
						'WARNING: Dead acceptor:',
						acceptor_id, acceptor_proc,
					)

					self.remove_acceptor(acceptor_data)

					self.nprintf('Removed dead acceptor', acceptor_id)

				# Make sure there's a correct amount of acceptors
				while len(self.acceptor_pool) < self.acceptor_amount:
					self.create_acceptor()

				time.sleep(
					self.ACCEPTOR_MGE_STATUS_CHECK_INTERVAL_S
				)


		# All of this shit is one-way ONLY
		os._exit(1)



class JagNetworking(NamedPrint):
	def __init__(self, bind_addr, callback):
		# The 2 things this basically cannot exist without
		self.bind_addr = bind_addr
		self.callback = callback

	def mp(self, *args, **kwargs):
		try:
			MPNetworking(self.bind_addr, self.callback, *args, **kwargs).run()
		except Exception as e:
			dbg_print('FATAL:', str_exception(e))

	def threaded(self,
		*args,
		max_workers=None,
		con_hard_limit=None,
		use_better_timers=True,

		# Everything else is session config
		**kwargs,
	):
		skt = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		skt.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		if REUSEPORT_AVAILABLE:
			skt.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
		skt.bind(self.bind_addr)
		skt.listen(con_hard_limit or 337)

		thread_pool = ThreadPoolExecutor(
			max_workers=max_workers or 37
		)

		if use_better_timers:
			timer_sched = FasterTimerSched()
			kwargs['better_timer'] = timer_sched.timer

		while True:
			try:
				cl_con, cl_addr = skt.accept()
				self.nprintf('Got connection:', cl_con)
			except Exception as e:
				print_exception_framed(e)
				time.sleep(0.1)
				continue

			thread_pool.submit(
				JagSession(
					cl_con,
					self.callback,

					**kwargs,
				)
				.run_auto
			)

		thread_pool.shutdown(wait=True)




