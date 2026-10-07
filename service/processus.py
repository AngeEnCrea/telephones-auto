"""processus.py : un programme de go-ios qui doit tourner en continu (le tunnel iOS 17+, l'agent d'un téléphone, le
relais de son écran). Lancé, surveillé ; ses dernières lignes sont gardées pour dire ce qui cloche. La
relance est décidée par qui le possède (appareil.py, parc.py), qui sait si ça vaut la peine.

Sur le PC, le service se range dans un Job Object Windows « tué à la fermeture » (voir attacher_au_service) : si le
service meurt, même tué net par le Planificateur, tous ses go-ios meurent avec lui. Sans ça, un vieux tunnel
survivant garderait ses ports et le suivant ne démarrerait plus."""
import asyncio
import collections
import ctypes
import logging
import os
import subprocess
import sys
import time

import goios


class Processus:
    def __init__(self, nom, args):
        self.nom = nom
        self.args = [str(a) for a in args]
        self.proc = None
        self.lignes = collections.deque(maxlen=80)
        self.depuis = None
        self.code = None          # code de sortie de la dernière fois
        self.fini_le = 0
        self.volontaire = False   # arrêté par nous (relance) : son code de sortie ne dit rien d'une panne
        self.log = logging.getLogger(nom)

    @property
    def tombe(self):
        """Il s'est arrêté seul, en erreur."""
        return not self.vivant and self.code not in (None, 0) and not self.volontaire

    @property
    def vivant(self):
        return self.proc is not None and self.proc.returncode is None

    async def demarrer(self):
        if self.vivant:
            return
        self.lignes.clear()
        self.code = None
        self.volontaire = False
        self.proc = await asyncio.create_subprocess_exec(
            *self.args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            creationflags=goios.SANS_FENETRE, limit=1 << 20)
        self.depuis = time.time()
        self.log.info("lancé (pid %s) : %s", self.proc.pid, " ".join(self.args[1:]))
        asyncio.create_task(self._lire(self.proc.stdout))
        asyncio.create_task(self._lire(self.proc.stderr))
        asyncio.create_task(self._attendre(self.proc))

    async def _lire(self, flux):
        try:
            async for brut in flux:
                ligne = brut.decode("utf-8", "replace").rstrip()
                if ligne:
                    self.lignes.append(ligne)
        except (ValueError, ConnectionError):
            pass

    async def _attendre(self, proc):
        code = await proc.wait()
        if proc is self.proc:
            self.code, self.fini_le = code, time.time()
            if self.volontaire:
                self.log.info("arrêté")
            else:
                self.log.warning("tombé (code %s)%s", code, f" : {self.dernier_message()}" if code else "")

    async def arreter(self):
        if not self.vivant:
            return
        self.volontaire = True
        self.proc.terminate()
        try:
            await asyncio.wait_for(self.proc.wait(), 8)
        except asyncio.TimeoutError:
            self.proc.kill()
            await self.proc.wait()

    def messages(self):
        return goios.messages("\n".join(self.lignes))

    def dit(self, *mots):
        return goios.contient(self.messages(), *mots)

    def dernier_message(self):
        return goios.resume(self.messages())

    def age(self):
        return time.time() - self.depuis if self.depuis else 0


def attacher_au_service():
    """Range le service (et donc tous les processus qu'il lancera) dans un Job Object « tué à la fermeture »."""
    if sys.platform != "win32":
        return
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class Base(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", ctypes.c_uint32), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", ctypes.c_uint32),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", ctypes.c_uint32),
                    ("SchedulingClass", ctypes.c_uint32)]

    class ES(ctypes.Structure):
        _fields_ = [(n, ctypes.c_uint64) for n in ("R", "W", "O", "RT", "WT", "OT")]

    class Etendues(ctypes.Structure):
        _fields_ = [("Base", Base), ("IoInfo", ES), ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t)]

    k32.CreateJobObjectW.restype = ctypes.c_void_p
    k32.GetCurrentProcess.restype = ctypes.c_void_p
    job = ctypes.c_void_p(k32.CreateJobObjectW(None, None))
    info = Etendues()
    info.Base.LimitFlags = 0x2000   # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info))
    if not k32.AssignProcessToJobObject(job, ctypes.c_void_p(k32.GetCurrentProcess())):
        logging.getLogger("service").warning("Job Object refusé (erreur %s) : un go-ios pourrait survivre au service",
                                             ctypes.get_last_error())
    attacher_au_service.job = job   # la poignée reste ouverte tant que le service vit
    os.environ["TELEPHONES_JOB"] = "1"
