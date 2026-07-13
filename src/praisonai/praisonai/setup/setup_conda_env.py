"""C10 shim: conda training-env setup moved to ``praisonai_train.setup.setup_conda_env``.

Kept so the ``setup-conda-env`` console script and
``praisonai.setup.setup_conda_env.main`` imports keep working.
"""

from praisonai._bootstrap import ensure_praisonai_train

ensure_praisonai_train()

from praisonai_train.setup.setup_conda_env import main  # noqa: F401

if __name__ == "__main__":
    main()
