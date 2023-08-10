import threading, io, time, multiprocessing, traceback, socket

_print = print

def print(*args):
	# return
	_print(*args)

# The log payload is: 
# int-log_data
# log_data:
# 	pickled log class


# Log class format is:
# lc.time:datetime.datetime = timestamp of the request
# lc.method:str = request method
# lc.httpver:str = http version
# lc.path:str = request path
# lc.usragent:str = useragent
# lc.ref:str = referer
# lc.addr_info = tuple(ip, port)


class stasi:
	"""
	Simple logger.
	Logs are stored in the user defined/default folder.
	Folder
		- logfile.log
		- previous_logfile.zip

	Log file format:
	[timestamp], ip:port
		method httpver
		path
		useragent
		referer|-
	"""
	def __init__(self, sv_resources):
		self.sv_res = sv_resources
		self.queue = []
		self.log_dir = sv_resources.cfg['logging']['logs_dir']
		self.log_file = self.log_dir / 'test.log'

		# init the processor
		threading.Thread(target=processor, args=(self,), daemon=True).start()

	# queue 
	def accept_log_record(self, cl_con, cl_addr):
		# first of all collect the payload
		try:
			print('accepting record')
			# buffer for the payload
			buf = io.BytesIO()

			# get the length of the payload
			while True:
				print('receiving length of the request payload')
				data = cl_con.recv(4)
				print('received data:', data)
				buf.write(data)
				if buf.tell() < 4:
					continue
				else:
					break
			# convert received bytes to int
			buf.seek(0, 0)
			p_len = int.from_bytes(buf.read(4), 'little') - 4
			buf.seek(0, 2)

			# receive the remaining payload according to its length
			while True:
				if buf.tell() >= p_len:
					break
				buf.write(cl_con.recv(65535))

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
			print(
				''.join(
					traceback.format_exception(
						type(err),
						err,
						err.__traceback__
					)
				)
			)




def write_log_record(recbytes, tgt_file):
	try:
		import pickle

		log_record = pickle.loads(recbytes)

		with open(str(tgt_file), 'a', encoding='utf-8') as write_tgt:
			write_tgt.write(f'[{log_record.time.isoformat()}], {log_record.addr_info[0]}:{log_record.addr_info[1]}\n')
			write_tgt.write('\t' + f'{log_record.method.upper()} {log_record.httpver}' + '\n')
			write_tgt.write('\t' + log_record.path + '\n')
			write_tgt.write('\t' + (log_record.usragent or '-') + '\n')
			write_tgt.write('\t' + (log_record.ref or '-'))
			write_tgt.write('\n\n')
	except Exception as err:
		print(
			''.join(
				traceback.format_exception(
					type(err),
					err,
					err.__traceback__
				)
			)
		)

# The processor keeps an eye on the queue and processes items piled up in it
def processor(log_ctrl):
	while True:
		try:
			# if the queue is empty - wait 1 second and try again
			if len(log_ctrl.queue) <= 0:
				time.sleep(1)

			for _ in range(len(log_ctrl.queue)):
				# get the record from the queue
				record = log_ctrl.queue[0]
				# first 4 bytes are garbage data, skip them
				record.seek(4, 0)
				# read everything past the mentioned 4 bytes
				record_bytes = record.read()
				# delete the record from the queue
				del log_ctrl.queue[0]
				# multiprocessing helps releave some load on this single-threaded mechanism
				task = multiprocessing.Process(target=write_log_record, args=(record_bytes, log_ctrl.log_file,), daemon=True)
				task.start()
				task.join()
		except Exception as err:
			print(
				''.join(
					traceback.format_exception(
						type(err),
						err,
						err.__traceback__
					)
				)
			)


# listener accepting incoming requests
def gestapo(sv_resources, sock_obj):
	# start listening the socket
	sock_obj.listen(0)

	# initialize the log controller
	# this class contains the queue and a method for accepting new queue items
	try:
		log_ctrl = stasi(sv_resources)
	except Exception as e:
		print(
			''.join(
				traceback.format_exception(
					type(err),
					err,
					err.__traceback__
				)
			)
		)
		raise e
	

	# listen for incoming log records connections
	while True:
		conn, address = sock_obj.accept()
		print('Got logger request')
		try:
			threading.Thread(target=log_ctrl.accept_log_record, args=(conn, address), daemon=True).start()
		except ConnectionAbortedError as err:
			pass
		except ConnectionResetError as err:
			pass
		except Exception as err:
			print(
				''.join(
					traceback.format_exception(
						type(err),
						err,
						err.__traceback__
					)
				)
			)












