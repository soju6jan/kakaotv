setting = {
    'filepath' : __file__,
    'use_db': True,
    'use_default_setting': True,
    'home_module': 'program',
    'menu': {
        'uri': __package__,
        'name': '카카오TV',
        'list': [
            {
                'uri': 'program',
                'name': '프로그램별',
                'list': [
                    {'uri': 'setting', 'name': '설정'},
                    {'uri': 'select', 'name': '선택'},
                    {'uri': 'queue', 'name': '큐'},
                    {'uri': 'list', 'name': '목록'},
                ]
            },
            {
                'uri': 'recent',
                'name': '최근 방송 자동 스케쥴링',
                'list': [
                    {'uri': 'setting', 'name': '설정'},
                ]
            },
        ]
    },
    'default_route': 'normal',
}
from plugin import *

P = create_plugin_instance(setting)
from .mod_program import ModuleProgram
from .mod_recent import ModuleRecent

P.set_module_list([ModuleProgram, ModuleRecent])
