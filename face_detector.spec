# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['face_detector.py'],
    pathex=[],
    binaries=[],
    datas=[('deploy.prototxt.txt', '.'), ('res10_300x300_ssd_iter_140000.caffemodel', '.'), ('icon.png', '.'), ('config.ini', '.'), ('C:\\\\Program Files\\\\Python313\\\\Lib\\\\site-packages\\\\cv2\\\\data\\\\haarcascade_frontalface_default.xml', 'cv2/data')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='face_detector',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
