from support.site import SupportKakaotv

from .mod_program import ModelKakaotvProgram
from .setup import *

name = 'recent'
 

class ModuleRecent(PluginModuleBase):
    
    def __init__(self, P):
        super(ModuleRecent, self).__init__(P, 'setting', scheduler_desc="카카오TV 최근 영상 큐에 넣기")
        self.name = name
        self.db_default = {
            f"{self.name}_db_version": "1",
            f"{self.name}_interval": "30",
            f"{self.name}_auto_start": "False",
        }
        self.current_download_count = 0
        

    def process_menu(self, page_name, req):
        arg = P.ModelSetting.to_dict()
        if page_name == 'setting':
            arg['is_include'] = scheduler.is_include(self.get_scheduler_id())
            arg['is_running'] = scheduler.is_running(self.get_scheduler_id())
        return render_template(f'{P.package_name}_{name}_{page_name}.html', arg=arg)


    def process_command(self, command, arg1, arg2, arg3, req):
        pass


    def scheduler_function(self):
        P.logger.error("scheduler_function")
        item_list = SupportKakaotv.get_recent_channel()

        for item in item_list:
            vod_list = SupportKakaotv.get_video_list(item['channel_id'])
            if vod_list == None or len(vod_list) == 0:
                continue
            db_item = ModelKakaotvProgram.get(vod_list[0]['clip_id'])
            if db_item != None and db_item.call == 'auto':
                logger.debug(f"{db_item.info['title']} exist")
                continue
            new = ModelKakaotvProgram(vod_list[0]['clip_id'], vod_list[0], call='auto')
            new.save()
            new.init_for_queue()
            self.get_module('program').download_queue.put(new)
