import threading, io, time, multiprocessing, socket
from jag_util import print_exception
from pathlib import Path

_print = print
def print(*args):
	return
	_print(*args)



# Logs are processed by a separate process, aka log server (this file):
# 	- Log records are sent to the log server through sockets.
# 	- The port of the log server is stored in os.environ['jag_logging_port']
# 	- Records can be sent to the log server by various modules of the server.
# 	- The payload sent to the log server consists of:
# 		- 4-byte long int indicating the size of the payload
# 		- Actual payload data: Pickled LogRecord

# There are different log types, see description of LogRecord
class LogRecord:
	"""\
	A standard log record.

	record_type:int
		1 - connection log
		2 - internal error log
		3 - user (room) error log
		4 - custom error log

	record_data:any=None
		Initial log record data
	"""
	def __init__(self, record_type:int, record_data=None, dtime=None):
		self.record_type = record_type
		self.log_data = record_data or {}

		# create timestamp
		# timestamp is datetime.datetime.now()
		try:
			self.timestamp = dtime.datetime.now()
		except Exception as e:
			pass
		if not dtime:
			import datetime
			self.timestamp = datetime.datetime.now()
		if isinstance(dtime, str):
			self.timestamp = dtime

	def push(self):
		"""\
		Push record to the logging server
		"""
		self.push = None
		import socket, pickle, os, time

		for attempt in range(3):
			try:
				# connect to the logger and send logging data
				with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as skt:
					logging_port = os.environ.get('jag_logging_port')
					if not logging_port:
						return
					skt.connect(
						( '127.0.0.1', int(logging_port) )
					)
					pdata = pickle.dumps(self)
					skt.sendall(len(pdata).to_bytes(4, 'little'))
					skt.sendall(pdata)
				return
			except Exception as e:
				time.sleep(1)
				continue



class LogRecordFormatter:
	"""\
	Format log record to text according to its type.

	Formats:
		1 - connection
			[timestamp], ip:port > response-code
				method httpver
				path
				useragent|-
				referer|-

		2 - internal error
			[timestamp]
			python error traceback
	"""
	def __init__(self, log_record:LogRecord):
		self.record_type = log_record.record_type
		self.data = log_record.log_data
		self.record_timestamp = log_record.timestamp

		type_suffix = {
			1: 'conlog',
			2: 'internal_err',
			3: 'usr_err',
			4: 'custom_log',
		}
		self.type_suffix = type_suffix.get(self.record_type, 'unknown_type')

	# convenience function
	def __str__(self):
		return self.to_text()

	# Format record to text
	def to_text(self):
		import io
		self.buf = io.StringIO()

		formats = {
			1: self.frmt_connection,
			2: self.frmt_internal_error,
			3: self.frmt_usr_error,
		}
		formatter = formats.get(self.record_type)

		if not formatter:
			return f'unsupported log format: >{self.record_type}<\n'
		else:
			try:
				return formatter()
			except Exception as e:
				print_exception(e)
				return f'Error occured while formatting log to text: >{e}<\n'


	# Util
	# =================

	def write_line(self, text, tgt=None, indent=0):
		tgt = tgt or self.buf
		for ln in str(text).split('\n'):
			tgt.write(
				('\t'*indent) + ln + '\n'
			)


	# Formatters
	# =================

	# Format connection log
	# Aka client connection log
	def frmt_connection(self):
		"""
		Data is a dict where
			- time:str        > datetime.datetime timestamp of when the request was accepted by the server
			- addr_info:tuple > (ip, port) of the client
			- method:str      > request method (post, get...)
			- httpver:str     > http version of the request (HTTP/1.1)
			- path:str        > request path
			- usragent:str    > User-Agent string
			- ref:str         > Referer string
			- rsp_code:int    > Response code
		"""

		dt = self.data
		write_line = self.write_line

		write_line(
			f"""[{dt['time'].isoformat()}], {dt['addr_info'][0]}:{dt['addr_info'][1]} > {dt['rsp_code']}"""
		)
		# method + http version
		write_line(f"""{dt['method'].upper()} {dt['httpver']}""", indent=1)
		# request path
		write_line(dt['path'], indent=1)
		# useragent header
		write_line(dt['usragent'] or '-', indent=1)
		# referer header
		write_line(dt['ref'] or '-', indent=1)
		# double break (end)
		write_line('')

		return self.buf.getvalue()

	# Format internal error
	# When something goes wrong inside jag itself
	def frmt_internal_error(self):
		"""
		Data is the error itself.
		"""
		from jag_util import traceback_to_text

		self.write_line(f'[{self.record_timestamp.isoformat()}]')
		self.write_line(self.data)

		return self.buf.getvalue()

	# Format internal error
	# When something goes wrong inside jag itself
	def frmt_usr_error(self):
		"""
		Data is the error itself.
		"""
		from jag_util import traceback_to_text

		self.write_line(f'[{self.record_timestamp.isoformat()}]')
		self.write_line(self.data)

		return self.buf.getvalue()




# The CEO of log server
class Stasi:
	"""\
	Simple logger.
	Logs are stored in the user defined/default folder.
	The name scheme of the log files is as follows:
		jag_log.[log_type].[seq_num].[ext]
	"""
	def __init__(self, sv_resources):
		self.sv_res = sv_resources
		self.queue = []
		self.log_dir = sv_resources.cfg['logging']['logs_dir']
		self.log_file = self.log_dir / 'test.log'

		# init the processor
		threading.Thread(target=log_records_processor, args=(self,), daemon=True).start()

	# queue 
	def accept_log_record(self, cl_con:socket.socket, cl_addr:tuple[str, int]):
		# first of all collect the payload
		try:
			print('accepting record')
			# buffer for the payload
			buf = io.BytesIO()

			# socket file
			skt_file = cl_con.makefile('rb', buffering=0)

			# get the length of the payload
			p_len = int.from_bytes(skt_file.read(4), 'little')
			print(
				'Log record payload length:', p_len
			)

			# receive the remaining payload according to its length
			buf.write(skt_file.read(p_len))

			print('appended record')
			# append record to the queue
			self.queue.append(buf)

			# close the connection
			cl_con.shutdown(socket.SHUT_RDWR)
		except ConnectionAbortedError as err:
			pass
		except ConnectionResetError as err:
			pass
		except Exception as err:
			print_exception(err)



# dump a group of log records to a file
# this function is being run every n seconds as a subprocess
def dump_log_record_batch(batch:list[bytes], tgt_dir:Path):
	# first, evaluate pickled data
	import pickle

	for recbytes in batch:
		log_record = LogRecordFormatter(pickle.loads(recbytes))

		tgt_file = tgt_dir / f'jag_log.{log_record.type_suffix}.log'

		# Write formatted data to file
		with open(str(tgt_file), 'a', encoding='utf-8') as write_tgt:
			write_tgt.write(
				log_record.to_text()
			)


# The processor keeps an eye on the queue and processes items piled up in it
# This function runs as a thread in a loop from the very beginning of the program
# and only terminates when the server shuts down
def log_records_processor(log_ctrl):
	import jag_util

	while True:
		if len(log_ctrl.queue) >= 4096:
			# Something went very wrong
			# Todo: really ?
			log_ctrl.queue = []
			return

		# if the queue is empty - wait 1 second and try again
		if len(log_ctrl.queue) <= 0:
			time.sleep(1)
			continue

		# spawning a process for every record is absolutely terrible
		# collect a number of records and process them in groups
		log_batch = []
		for idx in range(jag_util.clamp(len(log_ctrl.queue), 0, 64)):
			# first 4 bytes are garbage data, skip them
			log_ctrl.queue[0].seek(4, 0)

			# append good data to the batch
			log_batch.append(log_ctrl.queue[0].read())
			# delete the record from the queue
			del log_ctrl.queue[0]

		# Start the process
		task = multiprocessing.Process(
			target=dump_log_record_batch,
			args=(log_batch, log_ctrl.log_dir,),
			daemon=True
		)
		task.start()
		task.join()


# Bsically the root of the logging server
# this function creates a Stasi class (log server manager)
# and listens for incoming connections
def jag_log_server_process(sv_resources, sock_obj:socket.socket):
	import os

	# start listening the socket
	sock_obj.listen(0)

	_print('Logging PID:', os.getpid())

	# initialize the log controller
	# this class contains the queue and a method for accepting new queue items
	log_ctrl = Stasi(sv_resources)

	# listen for incoming log records connections
	while True:
		try:
			conn, address = sock_obj.accept()
			print('Got logger request')
			threading.Thread(
				target=log_ctrl.accept_log_record,
				args=(conn, address),
				daemon=True
			).start()
		except ConnectionAbortedError as err:
			pass
		except ConnectionResetError as err:
			pass
		except Exception as err:
			print_exception(err)












