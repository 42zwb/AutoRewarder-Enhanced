# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files


a = Analysis(
    ['AutoRewarder.py'],
    pathex=[],
    binaries=[],
    datas=[('gui', 'gui'), ('assets', 'assets')] + collect_data_files('nlpaug'),
    hiddenimports=[
        'selenium.webdriver.edge.webdriver',
        'pystray',
        'pystray._win32',
        'PIL',
        'PIL.Image',
        'nlpaug.augmenter.char',
        'nlpaug.model.char',
        'src.mobiletasks',
        'src.mobiletasks.client',
        'src.mobiletasks.models',
        'src.mobiletasks.oauth',
        'src.mobiletasks.runner',
        'src.mobiletasks.secure_store',
        'src.mobiletasks.tasks',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # The source only uses nlpaug's character keyboard augmenter. The base
    # Anaconda environment also contains optional ML/Qt/Jupyter stacks which
    # PyInstaller would otherwise discover through nlpaug and package into a
    # very large, slow build.
    excludes=[
        'torch', 'torchvision', 'tensorflow', 'keras', 'onnx', 'onnxruntime',
        'sklearn', 'scipy', 'matplotlib', 'pandas', 'PyQt5', 'PyQt6',
        'PySide6', 'IPython', 'jupyter', 'notebook', 'nbconvert', 'plotly',
        'dash', 'bokeh', 'panel', 'skimage', 'shapely', 'dask', 'numba',
        'llvmlite', 'pyarrow', 'h5py', 'statsmodels', 'xarray', 'playwright',
        'sqlalchemy', 'sympy',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AutoRewarder',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets\\icon.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='AutoRewarder',
)
