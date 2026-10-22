#!/usr/bin/env python3
"""Build the TN acados solvers in place and stamp plugin.json with this platform. Run ON THE TARGET (the comma
device, same openpilot version) from an openpilot checkout's Python environment:

  cd /data/openpilot && PYTHONPATH=/data/openpilot python3 <xpilot-plugins>/plugins/tn_long/build_native.py

Mirrors the old openpilot/tesla/long/legacy_mpc/SConscript: generate C for both OCP models with acados_template,
compile libacados_ocp_solver_<model>.so, copy the acados runtime libs next to it (rpath $ORIGIN), cythonize and
compile acados_ocp_solver_pyx.so. Then rebuild the index in the repository root (tools/build_index.py).
"""
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import sysconfig

HERE = Path(__file__).resolve().parent
MPC = HERE / "legacy_mpc"
MODELS = (("sp_legacy_cruise_v1", "c_generated_code"), ("sp_legacy_cruise_v1_fallback", "c_generated_code_fallback"))
ACADOS_LIBS = ("libacados.so", "libblasfeo.so", "libhpipm.so", "libqpOASES_e.so.3.1")
CC = os.environ.get("CC", "clang")


def run(cmd: list[str], **kw) -> None:
  print("+", " ".join(cmd), flush=True)
  subprocess.run(cmd, check=True, **kw)


def generate(acados) -> None:
  os.environ.update(ACADOS_SOURCE_DIR=acados.DIR, ACADOS_PYTHON_INTERFACE_PATH=acados.TEMPLATE_DIR, TERA_PATH=acados.TERA_PATH)
  # load the plugin as a package so its relative imports resolve, without needing the compiled solvers
  spec = importlib.util.spec_from_file_location("tn_long_build", HERE / "__init__.py", submodule_search_locations=[str(HERE)])
  sys.modules["tn_long_build"] = importlib.util.module_from_spec(spec)
  long_mpc = importlib.import_module("tn_long_build.legacy_mpc.long_mpc")
  from acados.acados_template import AcadosOcpSolver
  AcadosOcpSolver.generate(long_mpc.generate_legacy_ocp(), json_file=long_mpc.JSON_FILE)
  AcadosOcpSolver.generate(long_mpc.generate_legacy_ocp(long_mpc.FALLBACK_MODEL_NAME, long_mpc.FALLBACK_EXPORT_DIR, long_mpc.N),
                           json_file=long_mpc.FALLBACK_JSON_FILE)


def build(acados, model: str, gen_name: str) -> None:
  import numpy as np
  gen = MPC / gen_name
  includes = [acados.INCLUDE_DIR, os.path.join(acados.INCLUDE_DIR, "blasfeo", "include"),
              os.path.join(acados.INCLUDE_DIR, "hpipm", "include"), str(gen)]
  inc = [f"-I{d}" for d in includes]
  # same build_files as the old SConscript
  sources = [str(gen / f) for f in (
    f"acados_solver_{model}.c",
    f"{model}_model/{model}_expl_ode_fun.c", f"{model}_model/{model}_expl_vde_forw.c",
    *(f"{model}_cost/{model}_cost_{k}_{f}.c" for k in ("y", "y_e", "y_0") for f in ("fun", "fun_jac_ut_xt", "hess")),
    f"{model}_constraints/{model}_constr_h_fun.c", f"{model}_constraints/{model}_constr_h_fun_jac_uxt_zt.c")]
  for lib in ACADOS_LIBS:
    shutil.copy2(Path(acados.LIB_DIR) / lib, gen / lib)
  rpath = ["-Wl,-rpath,$ORIGIN", "-Wl,--disable-new-dtags"]
  run([CC, "-shared", "-fPIC", "-O2", "-DACADOS_WITH_QPOASES", "-Wno-unused", *inc, *sources, "-o", str(gen / f"libacados_ocp_solver_{model}.so"),
       f"-L{acados.LIB_DIR}", "-lacados", "-lhpipm", "-lblasfeo", "-lqpOASES_e", "-lm", *rpath])
  pyx_c = gen / "acados_ocp_solver_pyx.c"
  run([sys.executable, "-m", "cython", "-o", str(pyx_c), "-I", str(gen), "-I", acados.TEMPLATE_DIR,
       os.path.join(acados.TEMPLATE_DIR, "acados_ocp_solver_pyx.pyx")])
  run([CC, "-shared", "-fPIC", "-O2", "-pthread", "-Wno-cpp", "-Wno-deprecated-declarations", *inc,
       f"-I{sysconfig.get_paths()['include']}", f"-I{np.get_include()}", str(pyx_c),
       "-o", str(gen / "acados_ocp_solver_pyx.so"), f"-L{gen}", f"-lacados_ocp_solver_{model}", *rpath])
  (gen / "__init__.py").touch()


def main() -> None:
  import acados
  generate(acados)
  for model, gen in MODELS:
    build(acados, model, gen)
  # keep only what the runtime loads: libraries, the Cython module and package markers
  for _, gen in MODELS:
    for p in (MPC / gen).rglob("*"):
      if p.is_file() and not (p.suffix == ".so" or ".so." in p.name or p.name == "__init__.py"):
        p.unlink()
    for d in sorted((p for p in (MPC / gen).rglob("*") if p.is_dir()), reverse=True):
      if not any(d.iterdir()):
        d.rmdir()
  for json_file in MPC.glob("acados_ocp_*.json"):
    json_file.unlink()
  manifest = HERE / "plugin.json"
  m = json.loads(manifest.read_text())
  m["platform"] = {"machine": platform.machine(), "python": sys.implementation.cache_tag}
  manifest.write_text(json.dumps(m, indent=2, ensure_ascii=False) + "\n")
  print("built for", m["platform"], "- now run tools/build_index.py in the repository root and commit")


if __name__ == "__main__":
  main()
