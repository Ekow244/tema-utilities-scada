"""Generate native Ignition 8.1 source resources; no Gateway export is fabricated."""
import csv
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'ignition'
PROJECT = BASE / 'project/TemaIgnition'
TAG = '[default]TemaTraining/'


def write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + '\n')


def manifest(folder, files):
    write(folder / 'resource.json', dict(scope='G', version=1, restricted=False,
                                       overridable=True, files=files, attributes={}))


def component(kind, name, props=None, basis='45px', bindings=None, **extra):
    result = dict(type=kind, version=0, meta=dict(name=name),
                  position=dict(basis=basis, shrink=0), props=props or {}, custom={})
    if bindings:
        result['propConfig'] = {key: dict(binding=value) for key, value in bindings.items()}
    result.update(extra)
    return result


def expression(value):
    return dict(type='expr', config=dict(expression=value))


def tag_binding(name):
    return dict(type='tag', config=dict(mode='direct', tagPath=TAG+name))


def label(name, text='', expr=None, size=16):
    return component('ia.display.label', name,
                     dict(text=text, style=dict(fontSize=size, color='#173b3a')),
                     bindings={'props.text': expression(expr)} if expr else None)


def button(name, text, call, enable):
    script = ('\ttry:\n\t\tresult = %s\n'
              '\t\tself.view.custom.commandStatus = "Accepted: %s"\n'
              '\texcept Exception as exc:\n'
              '\t\tself.view.custom.commandStatus = "Rejected: " + str(exc)\n') % (call, text)
    return component('ia.input.button', name, dict(text=text), basis='150px',
                     bindings={'props.enabled': expression(enable)},
                     events={'component': {'onActionPerformed': dict(type='script', scope='G',
                                                                      config=dict(script=script))}})


def build():
    mapping = [('Volume',100,'L'), ('Temperature',100,'degC'), ('Setpoint',100,'degC'),
               ('HeaterPercent',100,'%'), ('QualifiedHold',10,'s'), ('StateCode',1,''),
               ('SensorFault',1,''), ('InletOpen',1,''), ('DrainCommand',1,''),
               ('RinseOpen',1,''), ('SupplyVolume',100,'L')]
    raw = []
    scaled = []
    rows = []
    for offset, (name, divisor, unit) in enumerate(mapping):
        item = '[TemaSim]1.IRUS%d' % (offset+1)
        raw.append(dict(name=name, tagType='AtomicTag', valueSource='opc', dataType='Int4',
                        opcServer='Ignition OPC UA Server', opcItemPath=item, accessRights='Read_Only'))
        numeric = dict(name=name, tagType='AtomicTag', valueSource='expr', dataType='Float8',
                       expression='{[.]Raw/%s} / %s.0' % (name, divisor), engUnit=unit)
        if divisor == 1:
            numeric.update(dataType='Boolean' if name in ('SensorFault','InletOpen','DrainCommand','RinseOpen') else 'Int4',
                           expression=('{[.]Raw/%s} != 0' if name != 'StateCode' else '{[.]Raw/%s}') % name)
        numeric.update(historyEnabled=True, historyProvider='TemaHistory', sampleMode='Periodic',
                       historySampleRate=1, historySampleRateUnits='SEC', historicalDeadband=0.0)
        if name == 'Temperature':
            numeric['alarms'] = [dict(name='TemperatureHigh', priority='High', mode='AboveValue',
                                      setpointA=80.0, deadband=2.0, timeOnDelaySeconds=2.0, timeOffDelaySeconds=1.0)]
        if name == 'SensorFault':
            numeric['alarms'] = [dict(name='TemperatureSignalInvalid', priority='Critical', mode='Equality', setpointA=1)]
        if name == 'StateCode':
            numeric['alarms'] = [dict(name='BatchFaulted', priority='High', mode='Equality', setpointA=14)]
        scaled.append(numeric)
        rows.append([offset, offset+1, item, name, divisor, unit])
    from sys import path as sys_path
    sys_path.insert(0, str(ROOT))
    from scada.controller import State
    fault_code = list(State).index(State.FAULTED)
    next(t for t in scaled if t['name']=='StateCode')['alarms'][0]['setpointA'] = fault_code
    state_parts = ', '.join('%d,"%s"' % (i,s.value.title().replace('_',' ')) for i,s in enumerate(State))
    scaled.append(dict(name='StateName', tagType='AtomicTag', valueSource='expr', dataType='String', expression='case({[.]StateCode}, %s, "Unknown")' % state_parts))
    write(BASE / 'tags/tema-tags.json', {'tags':[dict(name='TemaTraining',tagType='Folder',
           tags=[dict(name='Raw',tagType='Folder',tags=raw)]+scaled)]})
    with (BASE / 'tags/modbus-map.csv').open('w', newline='') as f:
        writer=csv.writer(f); writer.writerow(['protocol_offset','ignition_address','opc_item_path','tag','divide_by','unit']);writer.writerows(rows)

    write(PROJECT / 'project.json', dict(title='Tema Utilities Lab · Ignition', description='Local Modbus training source; runtime verification pending',
                                       enabled=True, inheritable=False, parent=''))
    script = PROJECT / 'ignition/script-python/tema'
    manifest(script, ['code.py'])
    pages = PROJECT / 'com.inductiveautomation.perspective/page-config'
    manifest(pages, ['config.json'])
    write(pages / 'config.json', dict(pages={'/':dict(viewPath='Overview',title='Tema Utilities Lab')}, sharedDocks=dict(cornerPriority='top-bottom')))
    state = '{%sStateCode}' % TAG
    good = 'isGood(%s)' % state
    children = [label('Title','TEMA UTILITIES LAB · IGNITION',size=28),
                label('Scope','Local training project · actual Modbus I/O · independent portfolio simulation',size=13),
                label('State',expr='"Batch state: " + {%sStateName}' % TAG, size=22),
                label('Temperature',expr='"Temperature: " + toStr({%sTemperature}) + " degC"' % TAG, size=22),
                label('Quality',expr='if({%sSensorFault}, "SIMULATED SENSOR FAILURE · reject temperature for control", "Sensor flag healthy; check tag quality overlays for communication faults")' % TAG,size=13),
                label('Volume',expr='"Vessel: " + toStr({%sVolume}) + " / 120 L"' % TAG,size=20),
                label('Heater',expr='"Heater demand: " + toStr({%sHeaterPercent}) + " percent"' % TAG,size=20)]
    controls = component('ia.container.flex','Controls',dict(direction='row',wrap='wrap',style=dict(gap='10px')),basis='100px',children=[
        button('Prepare','Prepare standard','tema.prepare_standard()',good+' && ('+state+'=0 || '+state+'=9 || '+state+'=12 || '+state+'=%d)' % fault_code),
        button('Start','Start batch','tema.command("start")',good+' && '+state+'=0'),
        button('Pause','Pause','tema.command("pause")',good+' && '+state+'>=1 && '+state+'<=8'),
        button('Resume','Resume','tema.command("resume")',good+' && '+state+'=10'),
        button('Abort','Abort','tema.command("abort")',good+' && (('+state+'>=1 && '+state+'<=8) || '+state+'=10)'),
        button('SensorFault','Inject sensor fault','tema.command("sensor-fault")',good+' && '+state+'>=1 && '+state+'<=8')])
    children += [controls,label('CommandStatus',expr='{view.custom.commandStatus}',size=13)]
    pens=[]
    for name,color in [('Temperature','#18796e'),('Setpoint','#c79b59'),('Volume','#3984b4')]:
        pens.append(dict(name=name,enabled=True,visible=True,selectable=True,axis='',plot=0,
                         data=dict(source='histprov:TemaHistory:/drv:TemaIgnition:default:/tag:tematraining/'+name.lower()),
                         display=dict(type='line',styles=dict(normal=dict(stroke=dict(color=color,width=2))))))
    children.append(component('ia.chart.powerchart','History',dict(config=dict(mode='realtime',unitOfTime=5,measureOfTime='minutes'),pens=pens),basis='350px'))
    children.append(label('AlarmsTitle','Gateway alarm status · acknowledge and inspect native alarms',size=16))
    children.append(component('ia.display.alarmstatustable','Alarms',{},basis='260px'))
    view = dict(custom=dict(commandStatus='Ready'),params={},props=dict(defaultSize=dict(width=1200,height=1100)),
                root=component('ia.container.flex','root',dict(direction='column',style=dict(padding='24px',gap='10px',backgroundColor='#f3f5f2',overflow='auto')),children=children))
    view_folder = PROJECT / 'com.inductiveautomation.perspective/views/Overview'
    manifest(view_folder, ['view.json']); write(view_folder/'view.json',view)
    # Source archive, not a Designer-generated export or a .gwbk Gateway backup.
    out=BASE / 'dist'; out.mkdir(exist_ok=True)
    with zipfile.ZipFile(out/'TemaIgnition-source.zip','w',zipfile.ZIP_DEFLATED) as z:
        for file in sorted(PROJECT.rglob('*')):
            if file.is_file() and '__pycache__' not in file.parts and file.suffix != '.pyc':
                z.write(file,file.relative_to(PROJECT))
    print('Generated native project source, tag configuration, Modbus map and source archive.')


if __name__ == '__main__':
    build()
