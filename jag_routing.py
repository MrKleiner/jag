import inspect


from pathlib import (
	Path,
	PurePath,
)

from .jag_util import (
	print_exception_framed,
	NamedPrint,
)



class JagRoute(NamedPrint):
	ROUTE_PATH = None
	HANDLE_404 = False
	SET_HEADERS = None

	def run(self, req, rsp):
		pass



class JagRouter(NamedPrint):
	def __init__(self, route_classes):
		self.route_classes = tuple(
			(getattr(c, 'ROUTE_PATH', None), c) for c in route_classes

			if inspect.isclass(c)
			and issubclass(c, JagRoute)
		)

		for _, route_cls in self.route_classes:
			if getattr(route_cls, 'HANDLE_404', False) == True:
				self.handle_404 = route_cls
				break
		else:
			self.handle_404 = None

	def __call__(self, req, rsp):
		return self.match_request(req, rsp)

	def match_request(self, req, rsp):
		req_path = PurePath(req.query.path)
		callback_cls = None

		for route_wildcard, route_cls in self.route_classes:
			if not route_wildcard:
				continue

			if (route_wildcard == req.query.path) or req_path.match(route_wildcard):
				# callback_cls = getattr(route_cls, 'run', None)
				callback_cls = route_cls
				break
		else:
			# callback_cls = getattr(self.handle_404, 'run', None)
			callback_cls = self.handle_404

		if callback_cls:
			for hname, hval in (getattr(callback_cls, 'SET_HEADERS', ()) or ()):
				rsp.headers[hname] = hval

			# if '__init__' in callback_cls.__dict__:
			if hasattr( callback_cls, 'jag_init'):
				callback_cls = callback_cls()
				callback_cls.jag_init(req, rsp)
			else:
				callback_cls = callback_cls()

			if (run := getattr(callback_cls, 'run', None)):
				run(req, rsp)



