"""Run independent review probes against the immutable input-v1 snapshot."""

import json
import sys
from pathlib import Path
from threading import Event, Thread
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
SNAPSHOT = ROOT / ".worknote/implementation/review/input-v1"
sys.path.insert(0, str(SNAPSHOT))
sys.path.insert(0, str(SNAPSHOT / "tests"))
sys.stdout.reconfigure(encoding="utf-8")

import kubernetes
import kubernetes_client
from test_interface import InterfaceTests, response
from urllib3.response import HTTPResponse


def fixture():
    test = InterfaceTests()
    test.setUp()
    return test


def record(name, **values):
    print(json.dumps({"probe": name, **values}, ensure_ascii=False))


record("input", sdk=kubernetes.__version__, module=kubernetes_client.__file__)

for name, raw in (
    ("truncated_eof", b'{"type":"MODIFIED","object":'),
    ("utf8_replacement", b'{"type":"ADDED","object":{"metadata":'
     b'{"resourceVersion":"rv","name":"bad\xffname"}}}\n'),
):
    test = fixture()
    try:
        test.wire.result = lambda: response(raw)
        with test.client.pods.watch() as stream:
            events = list(stream)
        record(name, events=events, closed=stream._closed,
               response_closed=test.wire.responses[-1].closed)
    except Exception as error:
        record(name, error=type(error).__name__, message=str(error))
    finally:
        test.doCleanups()

test = fixture()
try:
    stream = test.client.pods.watch()
    with patch.object(stream._watch._api_client, "close") as sdk_close:
        iter(stream).close()
        record("unstarted_iterator_close", closed=stream._closed,
               registered=len(test.client._streams),
               sdk_close_calls=sdk_close.call_count)
finally:
    test.doCleanups()


class BlockingResponse(HTTPResponse):
    def __init__(self):
        super().__init__(body=b"", status=200, preload_content=False)
        self.entered = Event()
        self.resume = Event()
        self.released = False

    def stream(self, **options):
        self.entered.set()
        if not self.resume.wait(5):
            raise TimeoutError("Probe reader was not released")
        return
        yield

    def close(self):
        super().close()

    def release_conn(self):
        self.released = True


test = fixture()
reader_result = []
try:
    stream = test.client.pods.watch()
    blocked = BlockingResponse()
    test.wire.result = lambda: blocked

    def read():
        try:
            reader_result.append({"events": list(stream)})
        except Exception as error:
            reader_result.append({"error": type(error).__name__})

    reader = Thread(target=read, daemon=True)
    reader.start()
    assert blocked.entered.wait(5), "Reader did not enter response.stream"
    try:
        stream.stop()
        stop_error = None
    except Exception as error:
        stop_error = type(error).__name__ + ": " + str(error)
    record("concurrent_stop", stop_error=stop_error,
           closed_before_reader_resumes=stream._closed,
           registered_before_reader_resumes=len(test.client._streams))
    blocked.resume.set()
    reader.join(5)
    record("concurrent_stop_after_resume", reader_alive=reader.is_alive(),
           reader_result=reader_result, closed=stream._closed)
finally:
    test.doCleanups()

test = fixture()
try:
    test.wire.result = {
        "metadata": {"uid": "uid", "generation": 2},
        "spec": {"replicas": 1},
        "status": {
            "observedGeneration": 1,
            "conditions": [{"type": "Progressing", "status": "False",
                            "reason": "ProgressDeadlineExceeded"}],
        },
    }
    try:
        result = test.client.deployments.wait_ready(
            "demo", expected_uid="uid", target_generation=2,
        )
        record("stale_progress_failure", result=result)
    except Exception as error:
        record("stale_progress_failure", error=type(error).__name__,
               message=str(error),
               object_gets=sum(c[1].endswith("/deployments/demo")
                               for c in test.wire.calls))
finally:
    test.doCleanups()
