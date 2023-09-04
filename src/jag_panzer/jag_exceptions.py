


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
		



















