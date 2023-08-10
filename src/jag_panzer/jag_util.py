

def dict_pretty_print(d):
	return
	sex = '\n'
	for key in d:
		sex += f"""{('>' + str(key) + '<').ljust(30)} :: >{str(d[key])}<""" + '\n'

	print(sex)

def multireplace(src, replace_pairs):
	for replace_what, replace_with in replace_pairs:
		src = src.replace(replace_what, replace_with)
	return src


def clamp(num, tgt_min, tgt_max):
	return max(tgt_min, min(num, tgt_max))


def int_to_chunksize(i):
	return f"""{hex(i).lstrip('0x')}\r\n""".encode()


# get local IP of the machine
def get_current_ip():
	import socket
	# what the fuck ?
	return ([l for l in ([ip for ip in socket.gethostbyname_ex(socket.gethostname())[2] 
	if not ip.startswith("127.")][:1], [[(s.connect(('8.8.8.8', 53)), 
	s.getsockname()[0], s.close()) for s in [socket.socket(socket.AF_INET, 
	socket.SOCK_DGRAM)]][0][1]]) if l][0][0])


class excHook:
	"""
	For whatever reason, exceptions are not being printed in subprocesses
	"""
	def __init__(self, send_logs, mute):
		self.send_logs = send_logs
		self.mute = mute

	def __call__(self, etype, evalue, etb):
		self.handle((etype, evalue, etb))

	def handle(self, info=None):
		import sys, traceback
		info = info or sys.exc_info()
		"""
		print(
			''.join(
				traceback.format_exception(
					type(err),
					err,
					err.__traceback__
				)
			)
		)
		"""
		print(
			''.join(traceback.format_exception(*info))
		)

		try:
			self.echo_log(info)
		except Exception as e:
			pass
		

	# send error log to the logging server, if any
	def echo_log(self, info):
		import socket, pickle, os
		from jag_logging import logRecord

		if log_port == False or not self.send_logs:
			return

		err_record = logRecord(2, info)
		err_record.push()


def rebind_exception(send_logs=True, mute=False):
	import sys
	print('rebound traceback')
	sys.excepthook = excHook(send_logs, mute)


def print_exception(err):
	import traceback
	try:
		print(
			''.join(
				traceback.format_exception(
					type(err),
					err,
					err.__traceback__
				)
			)
		)
	except Exception as e:
		print(e)


def traceback_to_text(info):
	import traceback

	try:
		if not isinstance(info, tuple):
			return (
				''.join(
					traceback.format_exception(
						type(info),
						info,
						info.__traceback__
					)
				)
			)
		else:
			return ''.join(traceback.format_exception(*info))
	except Exception as e:
		return str(e) + ' ' + str(info)
