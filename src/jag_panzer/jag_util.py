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
	pass


def iterable_to_grouped_text(tgt, groupname:str='', indent:int=1) -> str:
	"""\
	Convert an itrable into a nice frame
	"""
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
	"""\
	Separate prints into groups, like so::

	    +--------------------------
	    |LOL
	    +--------------------------
	    | ('Printing text',)
	    | ('Printing more text',)
	    | ('Printing another text',)
	    +--------------------------
	"""
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


def progrssive_hash(buf, hash_function, mb_read:int=100, as_bytes:bool=False) -> str|bytes:
	"""\
	Progrssively calculate hash of a readable buffer.
	- hash_function must be a function from hashlib, such as
	md5, sha256, sha512 and so on.

	:param buf: Input readable buffer
	:param hash_function: hashlib.sha256/hashlib.md5 and so on
	:param mb_read: Amount of megabytes to read from the buffer per update
	:param as_bytes: Whether to return the digest as hex string or bytes
	:return:
	"""
	block_size = (1024**2)*mb_read
	digest = hash_function()
	while True:
		data = buf.read(block_size)
		if not data:
			break
		digest.update(data)

	if as_bytes:
		return digest.digest()
	else:
		return digest.hexdigest()

def multireplace(src:str|bytes, replace_pairs:list[tuple[str|bytes, str|bytes]]) -> str|bytes:
	"""
	Replace multiple entries at once.

	:param src: Source string/byte object
	:param replace_pairs: A list of tuples containing what to replace with what
	:return: Modified input
	"""
	for replace_what, replace_with in replace_pairs:
		src = src.replace(replace_what, replace_with)
	return src


def clamp(num:int|float, tgt_min:int|float, tgt_max:int|float) -> int|float:
	"""
	Clamp a number to a range.

	:param num: The number to clamp
	:param tgt_min: Clamp floor
	:param tgt_max: Clamp ceil
	:return: Either the number itself or the floor/ceil
	"""
	return max(tgt_min, min(num, tgt_max))


def int_to_chunksize(i:int) -> bytes:
	"""\
	Convert an integer into HTML chunk size.
	"""
	return f"""{hex(i).lstrip('0x')}\r\n""".encode()


# get local IP of the machine
def get_current_ip():
	"""\
	Get local IP of the machine this function was called on.

	A piece of code copypasted from a random website,
	which looks like it was either AI-generated or
	written by a chinese.
	Nontheless - it works.
	"""
	import socket
	# what the fuck ?
	# Why?
	# todo: Don't use this function, simply bind on all interfaces
	return ([l for l in ([ip for ip in socket.gethostbyname_ex(socket.gethostname())[2] 
	if not ip.startswith("127.")][:1], [[(s.connect(('8.8.8.8', 53)), 
	s.getsockname()[0], s.close()) for s in [socket.socket(socket.AF_INET, 
	socket.SOCK_DGRAM)]][0][1]]) if l][0][0])


class ExcHook:
	"""\
	For whatever reason, exceptions are not being printed in subprocesses.

	**THIS DOES NOT WORK, FUCK**
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
	"""Redundant"""
	import sys
	print('rebound traceback')
	sys.excepthook = ExcHook(send_logs, mute)


def print_exception(err):
	"""\
	For whatever reason - threading and multiprocessing
	don't print exceptions. Which means a print statement
	should explicitly print the desired text.

	This function takes an error object as an input
	and prints it as regular traceback.
	"""
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


def traceback_to_text(info) -> str:
	"""\
	Format traceback object into your regular
	traceback text. Just like the one python prints
	by default.
	"""

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


def multistring(*args) -> str:
	"""\
	Return the strings passed, but joined together
	"""
	return ''.join([*args])


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
	"""\
	Simple interface for launching and killing a process,
	which may or may not have non-daemonic children.

	The process in question must be stored in self.target_process

	This class can work with multiprocessing.Process and threading.Thread.

	External dependency: psutil
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
	def pid(self) -> int | None:
		if self.threaded:
			return None
		return self.target_process.pid

	@property
	def is_alive(self) -> bool:
		return self.target_process.is_alive()

	def restart(self):
		"""\
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


# important todo: Do NOT encode string stoppers to bytes
# and do NOT encode feed data to bytes when stopper is a string
# todo: The class is literally called ByteSequenceStopper,
# STOP ACCEPTING STRINGS
class ByteSequenceStopper:
	"""\
	Progressively detect a byte sequence from a byte stream.
	Keep feeding bytes to this class till it returns True.
	"""
	def __init__(self, target_sequence:bytes|str|bytearray):
		if not type(target_sequence) in (bytes, str, bytearray):
			raise TypeError(
				'Invalid sequence: the target sequence can only be one of (bytes, str, bytearray)'
				+
				f'and not {type(target_sequence)}'
			)

		if isinstance(target_sequence, str):
			target_sequence = target_sequence.encode()

		self.tgt_sequence:bytearray = bytearray(target_sequence)
		self.finished = False
		self.result = False

		# Index of the expected character
		self.expect = 0

		self.match_len = len(self.tgt_sequence) - 1

	def __enter__(self):
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		self.finished = True

	def close(self):
		self.finished = True

	def feed(self, data:bytes|str|bytearray) -> tuple[bool, bytes]:
		if self.finished:
			return self.result

		if isinstance(data, str):
			data = data.encode()

		for idx, char in enumerate(data):
			if self.expect == self.match_len:
				self.finished = True
				self.result = True
				return True, bytes(data[(idx+1):])

			if char == self.tgt_sequence[self.expect]:
				self.expect += 1
			else:
				self.expect = 0

		return False, b''





