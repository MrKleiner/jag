import os

def conlog(*args, loglvl=1, exact=False):
	env_lvl = int(os.environ.get('_jag-dev-lvl', 0))
	if exact and loglvl == env_lvl:
		print(*args)
		return

	if env_lvl >= loglvl:
		print(*args)



def dict_pretty_print(d):
	return
	sex = '\n'
	for key in d:
		sex += f"""{('>' + str(key) + '<').ljust(30)} :: >{str(d[key])}<""" + '\n'

	print(sex)


def iterable_to_grouped_text(tgt, groupname='', indent=1):
	indent = '\t'*indent

	result = '\n'
	result += f'{indent}+--------------------------\n'
	result += f'{indent}|{groupname}\n'
	result += f'{indent}+--------------------------\n'
	if isinstance(tgt, dict):
		for k, v in tgt.items():
			result += f'{indent}| {k}: {v}\n'

	if type(tgt) in (set, list, tuple):
		for v in tgt:
			result += f'{indent}| {v}\n'

	result += f'{indent}+--------------------------\n'
	return result


class DynamicGroupedText:
	def __init__(self, groupname='', indent=1):
		self.indent = '\t'*indent
		self.groupname = groupname

	def __enter__(self):
		conlog(f'\n{self.indent}+--------------------------')
		conlog(f'{self.indent}|{self.groupname}')
		conlog(f'{self.indent}+--------------------------')
		return self
		
	def __exit__(self, type, value, traceback):
		conlog(f'{self.indent}+--------------------------\n')

	def print(self, *args):
		conlog(f'{self.indent}| {args}')

def progrssive_hash(buf, hash_function, mb_read=100):
	block_size = (1024**2)*mb_read
	digest = hash_function()
	while True:
		data = buf.read(block_size)
		if not data:
			break
		digest.update(data)

	return digest.hexdigest()



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


# Todo: should this really be in util ?
class JagConfigBase:
	"""Class for creating configs with groups"""
	def reg_cfg_group(self, groupname, paramdict):
		self.cfg[groupname] = paramdict | self.cfg.get(groupname, {})

	def create_base(self, default_cfg=None, input_cfg=None):
		default_cfg = default_cfg or {}
		input_cfg = input_cfg or {}

		self.cfg = default_cfg | input_cfg


class NestedProcessControl:
	"""
	Simple interface for launching and killing a process,
	which may or may not have children.

	The process in question must be stored in self.target_process
	"""
	running = False
	threaded = False

	def terminate(self):
		"""Strike the process with a HIMARS."""
		self.target_process.terminate()
		self.running = False

		# psutil is much appreciated
		# And actually required to do this properly...
		# important todo: psutil dependency
		try:
			self._terminate_children_tree()
		except Exception as e:
			pass

	def _terminate_children_tree(self):
		import psutil
		current_process = psutil.Process()
		children = current_process.children(recursive=True)
		for child_proc in children:
			child_proc.terminate()

	@property
	def pid(self):
		return self.target_process.pid

	@property
	def is_alive(self):
		return self.target_process.is_alive()

	def restart(self):
		"""
		Restart the server.
		1 - Kill if possible
		2 - Start
		"""
		self.terminate()
		self.launch()
