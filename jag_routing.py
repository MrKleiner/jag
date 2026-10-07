import inspect
import fnmatch

from pathlib import (
	Path,
	PurePath,
)

try:
	from wcmatch import pathlib as wsm_pathlib
except ImportError:
	wsm_pathlib = None

from .jag_util import (
	print_exception_framed,
	NamedPrint,
)



class JagRoute(NamedPrint):
	ROUTE_PATH = None
	HANDLE_404 = False
	SET_HEADERS = None

	USE_FNMATCH = False

	# def jag_init(self, req, rsp):
	# 	pass

	# def run(self, req, rsp):
	# 	pass



class JagRouter(NamedPrint):
	def __init__(self, route_classes):
		# Filter out everything that is not a class and not a child of JagRoute,
		# so that it's possible to just pass globals().values()
		self.route_classes = tuple(
			# (getattr(c, 'ROUTE_PATH', None), c) for c in route_classes
			(c.ROUTE_PATH, c) for c in route_classes

			if inspect.isclass(c)
			and issubclass(c, JagRoute)
		)

		# Look for a 404 handler
		self.handle_404 = None
		for _, route_cls in self.route_classes:
			if route_cls.HANDLE_404 == True:
				self.handle_404 = route_cls

		# Check whether wcmatch is required
		for _, route_cls in self.route_classes:
			if (
				    not route_cls.HANDLE_404
				and not route_cls.USE_FNMATCH
				and not wsm_pathlib
			):
				raise ImportError(
					'wcmatch package required, but not installed '
					'(pip install wcmatch)'
				)

	def __call__(self, req, rsp):
		return self.match_request(req, rsp)

	def match_request(self, req, rsp):
		# req_path = PurePath(req.query.path)
		callback_cls = None

		for route_wildcard, route_cls in self.route_classes:
			if not route_wildcard:
				continue

			if route_wildcard == req.query.path:
				callback_cls = route_cls
				break

			if route_cls.USE_FNMATCH and fnmatch(req.query.path, route_wildcard):
				callback_cls = route_cls
				break

			if (
				wsm_pathlib.PurePath(
					req.query.path
				)
				.globmatch(
					route_wildcard,
					flags=wsm_pathlib.GLOBSTAR
				)
			):
				callback_cls = route_cls
				break
		else:
			callback_cls = self.handle_404

		if callback_cls:
			for hname, hval in (callback_cls.SET_HEADERS or ()):
				rsp.headers[hname] = hval

			callback_cls = callback_cls()
			if hasattr(callback_cls, 'jag_init'):
				callback_cls.jag_init(req, rsp)

			if (run := getattr(callback_cls, 'run', None)):
				run(req, rsp)



