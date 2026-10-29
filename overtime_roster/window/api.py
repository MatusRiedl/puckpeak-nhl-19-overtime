"""What the page can call: pywebview's js_api in the window, POST /api/<name> in browser mode.

EXPOSED is every call of the parts (app/registry.py: each part's CALLS) plus `ready`: the calls in docs/ui/*.md and
beta1's names (tools and re/scripts/oneclick_run.py call those). Each name runs the part that owns it
(Controller.calls); a call not built yet answers {"error": "not built yet"}. tests/test_api_surface.py checks that
the page's calls, the contract files' calls and beta1's names are all in it.

Every method answers quickly (work that takes a while runs as a job) and never raises: an unexpected error comes
back as {"error": ...} and is logged. A call that returns nothing answers {"ok": true}.
"""
from ..app import jobs, registry

EXPOSED = frozenset(registry.calls()) | {'ready'}


def _answer(run, args):
    try:
        reply = run(*args)
        return reply if reply is not None else {'ok': True}
    except Exception as err:  # never take the window down
        return {'error': jobs.log_unexpected(err)}


def _method(name):
    def call(self, *args):
        return _answer(self._c.calls[name], args)
    call.__name__ = name
    call.__qualname__ = f'Api.{name}'
    return call


class Api:
    EXPOSED = EXPOSED

    def __init__(self, controller, host):
        self._c = controller
        self._host = host

    def ready(self):
        """The page has loaded: start the pushes and send everything once."""
        def first():
            self._host.start_pushing()
            return self._host.first()
        return _answer(first, ())


# one method per call (pywebview lists the class's methods for the window's js_api)
for _name in sorted(EXPOSED - {'ready'}):
    setattr(Api, _name, _method(_name))
del _name
