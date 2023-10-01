import os

def conlog(*args, loglvl=1, exact=False):
	"""\
	Printing might eat precious milliseconds.
	This is also useful for separating console logs into groups.
	"""
	env_lvl = int(os.environ.get('_jag-dev-lvl', 0))
	if exact and loglvl == env_lvl:
		print(*args)
		return

	if env_lvl >= loglvl:
		print(*args)



def dict_pretty_print(d):
	return
	fuck = '\n'
	for key in d:
		fuck += f"""{('>' + str(key) + '<').ljust(30)} :: >{str(d[key])}<""" + '\n'

	print(fuck)


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


def progrssive_hash(buf, hash_function, mb_read:int=100):
	"""\
	Progrssively calculate hash of a readable buffer.
	- hash_function must be a function from hashlib, such as
	md5, sha256, sha512 and so on.
	"""
	block_size = (1024**2)*mb_read
	digest = hash_function()
	while True:
		data = buf.read(block_size)
		if not data:
			break
		digest.update(data)

	return digest.hexdigest()


def multireplace(src, replace_pairs:list[tuple[str, str]]):
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
	# Why?
	# todo: Don't use this function, simply bind on all interfaces
	return ([l for l in ([ip for ip in socket.gethostbyname_ex(socket.gethostname())[2] 
	if not ip.startswith("127.")][:1], [[(s.connect(('8.8.8.8', 53)), 
	s.getsockname()[0], s.close()) for s in [socket.socket(socket.AF_INET, 
	socket.SOCK_DGRAM)]][0][1]]) if l][0][0])


class ExcHook:
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
		from jag_logging import LogRecord

		if log_port == False or not self.send_logs:
			return

		err_record = LogRecord(2, info)
		err_record.push()


def rebind_exception(send_logs=True, mute=False):
	import sys
	print('rebound traceback')
	sys.excepthook = ExcHook(send_logs, mute)


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
	"""\
	Class for creating configs with groups.
	This allows for an easy creation of structure like::
	    {
	        'root_key1': 'root_key1',
	        'root_key2': 'root_key2',
	        ...

	        'group_name': {
	            'group_key': 'keyval',
	            'group_key1': 'keyval1',
	            ...
	        },
	        'group_name1': {
	            'group_key': 'keyval',
	            'group_key1': 'keyval1',
	        }
	        ...
	    }
	The whole point is that this way it's very easy to have default settings.
	The base structure should be defined with all the keys and groups
	that should be overwrited later with custom config.
	For instance::
	    class ServerConfig(JagConfigBase):
	        def __init__(self, custom_cfg):
	            self.create_base(
	                {
	                    'root_key1': 'val1',
	                    'root_key1': 'val1',
	                },
	                custom_cfg
	            )

	            self.reg_cfg_group(
	            	'group_name',
	            	{
	            		'group_val1': 'key1',
	            		'group_val2': 'key2',
	            		...
	            	}
	            )
	            ...

	reg_cfg_group looks for the corresponding key name in the
	custom_config and overwrites pre-defined default group keys
	with the ones it found in custom_config
	"""

	cfg:dict = {}

	def reg_cfg_group(self, groupname:str, paramdict:dict):
		self.cfg[groupname] = paramdict | self.cfg.get(groupname, {})

	def create_base(self, default_cfg:dict=None, input_cfg:dict=None):
		default_cfg = default_cfg or {}
		input_cfg = input_cfg or {}

		self.cfg = default_cfg | input_cfg


class NestedProcessControl:
	"""
	Simple interface for launching and killing a process,
	which may or may not have non-daemonic children.

	The process in question must be stored in self.target_process.

	This class can work with multiprocessing.Process and threading.Thread.
	"""
	running:bool = False
	threaded:bool = False

	_target_process = None

	def terminate(self):
		"""Strike the process with a HIMARS."""

		# psutil is much appreciated
		# And actually required to do this properly...
		# important todo: psutil dependency
		if not self.threaded:
			try:
				self._terminate_children_tree()
			except Exception as e:
				pass

		self.target_process.terminate()
		self.running = False

	def _terminate_children_tree(self):
		"""\
		Terminate the children tree (when applicable)
		of the target_process with
		psutil (external dependency) (when applicable)
		"""
		import psutil
		current_process = psutil.Process(self.pid)
		children = current_process.children(recursive=True)
		for child_proc in children:
			child_proc.terminate()

	@property
	def pid(self) -> int:
		return self.target_process.pid

	@property
	def is_alive(self) -> bool:
		return self.target_process.is_alive()

	def restart(self):
		"""
		Restart the server.

		1 - Kill if possible

		2 - Start
		"""
		self.terminate()
		self.launch()

	def launch(self):
		from .jag_exceptions import LaunchFunctionIsNotDefined
		raise LaunchFunctionIsNotDefined(
			'The launch() method must be overwritten and start the process when called'
		)

	@property
	def	target_process(self):
		return self._target_process

	@target_process.setter
	def target_process(self, proc):
		import multiprocessing, threading
		"""
		if self._target_process is not None:
			from .jag_exceptions import TargetProcessWasAlreadySet
			raise TargetProcessWasAlreadySet(
				'The attribute target_process was already set'
			)
		"""

		if not type(proc) in (multiprocessing.Process, threading.Thread,):
			from .jag_exceptions import InvalidProcessType
			raise InvalidProcessType(
				'Invalid process type: target_process can only be one of'
				+
				f'(multiprocessing.Process, threading.Thread), but not {type(proc)}'
			)

		if type(proc) == threading.Thread:
			self.threaded = True

		self._target_process = proc







