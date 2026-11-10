"""Own only the processes created by this GUI instance; never invoke a shell."""

from __future__ import annotations

import codecs
from pathlib import Path
import time

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal


class ManagedProcess(QObject):
    output = Signal(str)
    exited = Signal(int)
    error = Signal(str)
    started = Signal()

    def __init__(self, parent=None, cwd=None):
        super().__init__(parent)
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        if cwd is not None:
            self.process.setWorkingDirectory(str(Path(cwd).resolve()))
        self.process.readyReadStandardOutput.connect(self._read_output)
        self.process.started.connect(self.started.emit)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._error)
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._stopping = False
        self._generation = 0
        self.graceful_line = "quit"

    def start(self, program: str, args=(), env=None) -> None:
        if self.is_running():
            raise RuntimeError("Ce processus est deja en cours d'execution.")
        self._generation += 1
        self._stopping = False
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        environment = QProcessEnvironment.systemEnvironment()
        if env is not None:
            if isinstance(env, QProcessEnvironment):
                environment = env
            else:
                for name, value in env.items():
                    if value is None:
                        environment.remove(str(name))
                    else:
                        environment.insert(str(name), str(value))
        self.process.setProcessEnvironment(environment)
        self.process.setProgram(str(program))
        self.process.setArguments([str(argument) for argument in args])
        # ReadWrite keeps stdin open for the simulator's existing set/quit IPC.
        self.process.start()

    def is_running(self) -> bool:
        return self.process.state() != QProcess.ProcessState.NotRunning

    def write_line(self, line: str) -> None:
        if self.process.state() != QProcess.ProcessState.Running:
            raise RuntimeError("Le processus n'est pas demarre.")
        if not isinstance(line, str) or "\n" in line or "\r" in line:
            raise ValueError("Une seule ligne de commande est autorisee.")
        if self.process.write((line + "\n").encode("utf-8")) < 0:
            raise RuntimeError("Ecriture vers le processus impossible.")

    def _read_output(self) -> None:
        data = bytes(self.process.readAllStandardOutput())
        if data:
            text = self._decoder.decode(data)
            if text:
                self.output.emit(text)

    def _finished(self, exit_code: int, exit_status) -> None:
        self._read_output()
        tail = self._decoder.decode(b"", final=True)
        if tail:
            self.output.emit(tail)
        self.exited.emit(exit_code)

    def _error(self, process_error) -> None:
        if self._stopping and process_error == QProcess.ProcessError.Crashed:
            return
        self.error.emit(self.process.errorString())

    def _terminate(self, generation: int) -> None:
        if generation == self._generation and self.is_running():
            self.process.terminate()

    def _kill(self, generation: int) -> None:
        if generation == self._generation and self.is_running():
            self.process.kill()

    def stop(self) -> None:
        """Request graceful exit, then TERM and KILL, without blocking Qt."""
        if not self.is_running() or self._stopping:
            return
        self._stopping = True
        generation = self._generation
        if self.process.state() == QProcess.ProcessState.Running:
            try:
                self.write_line(self.graceful_line)
            except RuntimeError:
                # The child may have closed its input just before Qt notices
                # process termination; signal escalation still owns cleanup.
                pass
            self.process.closeWriteChannel()
        QTimer.singleShot(350, self, lambda: self._terminate(generation))
        QTimer.singleShot(2350, self, lambda: self._kill(generation))

    def cleanup(self, timeout_ms: int = 3000) -> None:
        """Bounded final shutdown for closeEvent/aboutToQuit (not routine stop).

        Timer callbacks may no longer run when Qt is closing, so explicitly
        enforce the same escalation here and reap this child before returning.
        """
        timeout_ms = max(0, int(timeout_ms))
        deadline = time.monotonic() + timeout_ms / 1000

        def wait(maximum: int) -> bool:
            remaining = max(0, int((deadline - time.monotonic()) * 1000))
            return self.process.waitForFinished(min(maximum, remaining))

        self.stop()
        if not self.is_running() or wait(350):
            return
        self.process.terminate()
        if wait(1800):
            return
        self.process.kill()
        wait(timeout_ms)
