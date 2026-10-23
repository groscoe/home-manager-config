#!/usr/bin/python3
import os,sys,configparser,argparse
import secrets,select,shutil,subprocess,tempfile
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
os.environ['QT_QUICK_BACKEND']='software'
for key in ('QT_SCALE_FACTOR','QT_SCREEN_SCALE_FACTORS','QT_FONT_DPI','GDK_SCALE','GDK_DPI_SCALE'):
    os.environ.pop(key,None)
parser = argparse.ArgumentParser()
parser.add_argument('theme', type=Path)
parser.add_argument('output', type=Path)
parser.add_argument('--pyqt-extra', type=Path, help='Optional extracted Ubuntu PyQt5 QtQuick module for testing without installation')
parser.add_argument('--xvfb', default=shutil.which('Xvfb'), help='Xvfb executable for the disposable display')
parser.add_argument('--in-xvfb', action='store_true', help=argparse.SUPPRESS)
args = parser.parse_args()
if not args.in_xvfb:
    if not args.xvfb:
        parser.error('Install the optional xvfb test prerequisite or provide --xvfb')
    with tempfile.TemporaryDirectory(prefix='xps-host-ui-') as directory:
        scratch = Path(directory)
        auth = scratch/'auth'
        auth.write_bytes(b'')
        cookie = secrets.token_hex(16)
        def authorize(display):
            subprocess.run(['/usr/bin/xauth','-f',str(auth),'add',display,
                            'MIT-MAGIC-COOKIE-1',cookie],check=True,capture_output=True)
        authorize(':0')
        reader,writer = os.pipe()
        with (scratch/'xvfb.log').open('w') as log:
            server = subprocess.Popen([args.xvfb,'-displayfd',str(writer),'-screen','0',
                                       '1440x900x24','-nolisten','tcp','-auth',str(auth)],
                                      pass_fds=[writer],stdout=log,stderr=log)
            os.close(writer)
            try:
                if not select.select([reader],[],[],10)[0]:
                    raise RuntimeError('Xvfb did not start its disposable display')
                display = os.read(reader,128).decode().strip()
                if not display.isdigit():
                    raise RuntimeError('Xvfb failed: '+(scratch/'xvfb.log').read_text())
                display = ':'+display
                authorize(display)
                env = dict(os.environ,DISPLAY=display,XAUTHORITY=str(auth),
                           QT_QPA_PLATFORM='xcb',QT_QUICK_BACKEND='software')
                child = subprocess.run([sys.executable,'-I',str(Path(__file__).resolve()),
                                        *sys.argv[1:],'--in-xvfb'],env=env)
            finally:
                os.close(reader)
                server.terminate()
                try: server.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    server.kill(); server.wait()
        raise SystemExit(child.returncode)
import PyQt5
if args.pyqt_extra:
    PyQt5.__path__.append(str(args.pyqt_extra.resolve()))
from PyQt5.QtCore import QObject,Qt,QAbstractListModel,QModelIndex,pyqtProperty,pyqtSignal,pyqtSlot,QUrl,QPoint,QPointF,QMetaObject
from PyQt5.QtGui import QGuiApplication
from PyQt5.QtQuick import QQuickView
from PyQt5.QtTest import QTest

class Model(QAbstractListModel):
    def __init__(self,name):
        super().__init__(); self.name=name
    def rowCount(self,parent=QModelIndex()): return 1
    def roleNames(self): return {Qt.UserRole+1:b'name'}
    def data(self,index,role): return self.name if index.isValid() and role==Qt.UserRole+1 else None
    @pyqtProperty(int,constant=True)
    def lastIndex(self): return 0

class Keyboard(QObject):
    @pyqtProperty(bool,constant=True)
    def capsLock(self): return False

class Sddm(QObject):
    loginFailed=pyqtSignal()
    loginSucceeded=pyqtSignal()
    def __init__(self): super().__init__(); self.calls=[]
    @pyqtProperty(bool,constant=True)
    def canSuspend(self): return False
    @pyqtProperty(bool,constant=True)
    def canHibernate(self): return False
    @pyqtProperty(bool,constant=True)
    def canReboot(self): return False
    @pyqtProperty(bool,constant=True)
    def canPowerOff(self): return False
    @pyqtSlot(str,str,int)
    def login(self,user,password,session): self.calls.append((user,password,session))
    @pyqtSlot()
    def suspend(self): pass
    @pyqtSlot()
    def hibernate(self): pass
    @pyqtSlot()
    def reboot(self): pass
    @pyqtSlot()
    def powerOff(self): pass

theme=args.theme.resolve(); output=args.output.resolve(); output.mkdir(parents=True,exist_ok=True)
parser=configparser.ConfigParser(interpolation=None); parser.optionxform=str
parser.read([theme/'theme.conf',theme/'theme.conf.user'])
config={k:v.strip('"') for k,v in parser['General'].items()}
app=QGuiApplication([])
view=QQuickView(); view.engine().addImportPath('/usr/lib/x86_64-linux-gnu/qt5/qml')
user=Model('groscoe'); session=Model('i3'); keyboard=Keyboard(); sddm=Sddm()
for k,v in [('config',config),('userModel',user),('sessionModel',session),('keyboard',keyboard),('sddm',sddm)]:
    view.rootContext().setContextProperty(k,v)
view.setResizeMode(QQuickView.SizeRootObjectToView)
view.setSource(QUrl.fromLocalFile(str(theme/'Main.qml')))
assert view.status()==QQuickView.Ready,view.errors()
view.resize(1440,900); view.show(); QTest.qWait(500)
root=view.rootObject()
def find(name):
    obj=root.findChild(QObject,name); assert obj is not None,name; return obj
def prop(name,key): return find(name).property(key)
def enter_password():
    QMetaObject.invokeMethod(find('loginPassword'),'forceActiveFocus',Qt.DirectConnection)
    QTest.keyClick(view,Qt.Key_Return); QTest.qWait(50)
def screenshot(name):
    assert view.grabWindow().save(str(output/name))

def check_geometry():
    for name in ('fingerprintHint','authMessage','loginSubmit'):
        item=find(name); point=item.mapToItem(root,QPointF(0,0))
        assert point.x()>=0 and point.y()>=0,(name,point)
        assert point.x()+item.width()<=root.width()+1 and point.y()+item.height()<=root.height()+1,(name,point,item.width(),item.height())
    message=find('authMessage'); button=find('loginSubmit')
    assert message.mapToItem(root,QPointF(0,0)).y()+message.height() <= button.mapToItem(root,QPointF(0,0)).y(), 'Message overlaps login button'

assert prop('loginSubmit','enabled') and prop('loginSubmit','text')=='Use fingerprint'
assert 'press Enter' in prop('fingerprintHint','text') and prop('fingerprintHint','visible')
check_geometry(); screenshot('fingerprint-login-idle.png')
print('PASS: visible fingerprint action and Enter instructions; form fits the screen')
enter_password()
assert len(sddm.calls)==1 and sddm.calls[-1]==('groscoe','',0)
assert 'right index finger' in prop('authMessage','text') and prop('authSpinner','running')
assert not prop('loginSubmit','enabled')
check_geometry(); screenshot('fingerprint-login-waiting.png')
enter_password(); assert len(sddm.calls)==1
print('PASS: empty Enter requests fingerprint, shows waiting feedback and prevents duplicate submissions')
sddm.loginFailed.emit(); QTest.qWait(2200)
assert 'Fingerprint sign-in failed' in prop('authMessage','text')
assert prop('loginSubmit','enabled') and prop('loginPassword','enabled') and not prop('authSpinner','running')
check_geometry(); screenshot('fingerprint-login-retry.png')
print('PASS: reader failure restores controls and leaves a readable retry/password message')
button=find('loginSubmit'); point=button.mapToScene(QPointF(button.width()/2,button.height()/2))
before=len(sddm.calls); QTest.mouseClick(view,Qt.LeftButton,pos=point.toPoint()); QTest.qWait(50)
assert len(sddm.calls)==before+1 and sddm.calls[-1]==('groscoe','',0)
sddm.loginFailed.emit(); QTest.qWait(50)
print('PASS: the visible fingerprint button also starts fingerprint sign-in')
find('loginPassword').setProperty('text','synthetic-test-password')
assert prop('loginSubmit','text')!='Use fingerprint'
enter_password()
assert sddm.calls[-1]==('groscoe','synthetic-test-password',0)
assert prop('authMessage','text')=='Signing in…'
sddm.loginFailed.emit(); QTest.qWait(100)
assert prop('loginPassword','enabled')
print('PASS: typed passwords keep the normal password path')
find('loginPassword').setProperty('text',''); find('loginUsername').setProperty('text','another-user')
assert not prop('fingerprintHint','visible') and not prop('loginSubmit','enabled')
before=len(sddm.calls); enter_password(); assert len(sddm.calls)==before
print('PASS: fingerprint shortcut is shown only for the enrolled account')
print('All UI tests used a mock SDDM object. No real login, power action, credential or biometric data was used.')
view.setSource(QUrl()); view.close(); app.processEvents()
