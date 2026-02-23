import asyncio
import threading
from PySide6.QtCore import QObject, Signal
from chat_src.network.protocol import read_packet, send_packet

class ClientNode(QObject):
    connected = Signal()
    disconnected = Signal()
    error = Signal(str)
    packet_received = Signal(dict)

    def __init__(self, host: str, port: int):
        super().__init__()
        self.host = host
        self.port = port
        self._loop = None
        self._thread = None
        self._reader = None
        self._writer = None
        self._stop = threading.Event()

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._loop.stop)

    def send(self, pkt: dict):
        if not self._loop or not self._writer or self._loop.is_closed():
            return
        if not isinstance(pkt, dict):
            self.error.emit(f"send() expects dict, got {type(pkt)}")
            return
        fut = asyncio.run_coroutine_threadsafe(send_packet(self._writer, pkt), self._loop)
        fut.add_done_callback(lambda f: f.exception() if not f.cancelled() else None)

    def _run(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._main())
        except Exception as e:
            self.error.emit(str(e))
        finally:
            try:
                self._loop.close()
            except Exception:
                pass

    async def _main(self):
        try:
            self._reader, self._writer = await asyncio.open_connection(self.host, self.port)
        except Exception as e:
            self.error.emit(f"Connect failed: {e}")
            self.disconnected.emit()
            return

        self.connected.emit()

        while not self._stop.is_set():
            pkt = await read_packet(self._reader)
            if pkt is None:
                break
            self.packet_received.emit(pkt)

        try:
            self._writer.close()
            await self._writer.wait_closed()
        except Exception:
            pass

        self._writer = None
        self._reader = None
        self.disconnected.emit()