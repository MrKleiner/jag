

class PayloadTooLarge(Exception):
	"""Raised when a received payload is too large"""
	pass


class InvalidMultipartRequest(Exception):
	"""\
	Raised when client sends an invalid multipart request.
	This could be raised DURING the reading of the multipart message.
	"""
	pass


class MissingContentLength(Exception):
	"""\
	Raised when Content-Length header is required in
	the request, but not present.
	"""
	pass
		

class LaunchFunctionIsNotDefined(Exception):
	"""\
	Raised when the launch() method of NestedProcessControl
	was not overwritten.
	"""
	pass


class TargetProcessIsNotDefined(Exception):
	"""\
	Raised when self.target_process of NestedProcessControl was not overwritten.
	"""
	pass


class InvalidProcessType(Exception):
	"""\
	Raised when NestedProcessControl.target_process
	receives invalid process type.
	Only multiprocessing.Process and threading.Thread types
	are allowed
	"""
	pass


class TargetProcessWasAlreadySet(Exception):
	"""\
	Raise when attribute target_process of NestedProcessControl
	being set more than once.
	"""
	pass


class InvalidJagRoute(Exception):
	"""\
	Raised when JagRoute decorator was misconfigured.
	"""
	pass


class InvalidFormData(Exception):
	"""\
	Raised when client sends invalid form data.
	"""
	pass


class StopExecution(Exception):
	"""\
	Raised to stop any further client request evaluation
	"""
	pass








