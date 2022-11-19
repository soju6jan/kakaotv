import wv_tool
from support_site import SupportKakaotv

from .setup import *

name = 'program'

class ModuleProgram(PluginModuleBase):
    recent_code = None
    download_queue = None
    download_thread = None
    current_download_count = 0

    def __init__(self, P):
        super(ModuleProgram, self).__init__(P, 'select')
        self.name = name
        self.db_default = {
            f"{P.package_name}_{self.name}_last_list_option": "1",
            f"{self.name}_db_version": "1",
            f"{self.name}_recent_code": "",
            f"{self.name}_save_path": "{PATH_DATA}"+os.sep+"download",
            f"{self.name}_make_program_folder": "False",
            f"{self.name}_max_download_count": "2",
            f"{self.name}_quality": "1080p",
            f"{self.name}_failed_redownload": "False",
        }
        self.web_list_model = ModelKakaotvProgram
        default_route_socketio_module(self, attach='/queue')
        self.current_data = None


    def process_menu(self, page_name, req):
        arg = P.ModelSetting.to_dict()
        if page_name == 'select':
            tmp = request.args.get('code')
            if tmp != None:
                arg['code'] = tmp

        return render_template(f'{P.package_name}_{name}_{page_name}.html', arg=arg)


    def process_command(self, command, arg1, arg2, arg3, req):
        ret = {'ret':'success'}
        if command == 'analyze':
            match = re.search(r"channel/(?P<channel>\d+)/cliplink/(?P<clip>\d+)", arg1)
            if match:
                channel_id = match.group('channel')
                clip_id = match.group('clip')
            else:
                ret['ret'] = 'warning'
                ret['msg'] = "분석 실패"
                return jsonify(ret)
            self.current_data = SupportKakaotv.get_video_list(channel_id)
            P.ModelSetting.set(f"{self.name}_recent_code", arg1)
            return self.current_data
        elif command == 'previous_analyze':
            ret['data'] = self.current_data
        elif command == 'download_program':
            _pass = arg2
            db_item = ModelKakaotvProgram.get(arg1)
            if _pass == 'false' and db_item != None:
                ret['ret'] = 'warning'
                ret['msg'] = '이미 DB에 있는 항목입니다.'
            elif _pass == 'true' and db_item != None and ModelKakaotvProgram.get_by_id_in_queue(db_item.id) != None:
                ret['ret'] = 'warning'
                ret['msg'] = '이미 큐에 있는 항목입니다.'
            else:
                if db_item == None:
                    db_item = ModelKakaotvProgram(arg1, self.get_episode(arg1))
                    db_item.save()
                db_item.init_for_queue()
                self.download_queue.put(db_item)
                ret['msg'] = '다운로드를 추가 하였습니다.'
        elif command == 'download_program_check':
            lists = arg1[:-1].split(',')
            count = 0
            for _ in lists:
                db_item = ModelKakaotvProgram(_, self.get_episode(_))
                db_item.save()
                db_item.init_for_queue()
                self.download_queue.put(db_item)
            ret['msg'] = f"{len(lists)}개를 추가 하였습니다."
        elif command == 'queue_list':
            ret = [x.as_dict() for x in ModelKakaotvProgram.queue_list]
        elif command == 'program_list_command':
            if arg1 == 'remove_completed':
                count = ModelKakaotvProgram.remove_all(True)
                ret['msg'] = f"{count}개를 삭제하였습니다."
            elif arg1 == 'remove_incomplete':
                count = ModelKakaotvProgram.remove_all(False)
                ret['msg'] = f"{count}개를 삭제하였습니다."
            elif arg1 == 'add_incomplete':
                count = self.retry_download_failed()
                ret['msg'] = f"{count}개를 추가 하였습니다."
            elif arg1 == 'remove_one':
                result = ModelKakaotvProgram.delete_by_id(arg2)
                if result:
                    ret['msg'] = '삭제하였습니다.'
                else:
                    ret['ret'] = 'warning'
                    ret['msg'] = '실패하였습니다.'
        elif command == 'queue_command':
            if arg1 == 'cancel':
                queue_item = ModelKakaotvProgram.get_by_id_in_queue(arg2)
                queue_item.status = "CANCEL"
                wv_tool.WVDownloader.stop_by_callback_id(f"{P.package_name}_{self.name}_{arg2}")
            elif arg1 == 'reset':
                if self.download_queue is not None:
                    with self.download_queue.mutex:
                        self.download_queue.queue.clear()
                for _ in wv_tool.WVDownloader.get_list():
                    if _.callback_id.startswith(f"{P.package_name}_{self.name}"):
                        _.stop()
                ModelKakaotvProgram.queue_list = []
            elif arg1 == 'delete_completed':
                new = []
                for _ in ModelKakaotvProgram.queue_list:
                    if _.completed == False:
                        new.append(_)
                ModelKakaotvProgram.queue_list = new
        return jsonify(ret)


    def get_episode(self, clip_id):
        for _ in self.current_data:
            if _['clip_id'] == clip_id:
                return _


    def plugin_load(self):
        from sjva import Auth
        if Auth.get_auth_status()['ret'] == False:
            raise Exception('auth fail!')

        if self.download_queue is None:
            self.download_queue = queue.Queue()
        
        if self.download_thread is None:
            self.download_thread = threading.Thread(target=self.download_thread_function, args=())
            self.download_thread.daemon = True  
            self.download_thread.start()

        if P.ModelSetting.get_bool(f"{self.name}_failed_redownload"):
            self.retry_download_failed()
        

    def download_thread_function(self):
        while True:
            try:
                while True:
                    if self.current_download_count < P.ModelSetting.get_int(f"{self.name}_max_download_count"):
                        break
                    time.sleep(5)
                db_item = self.download_queue.get()
                if db_item.status == "CANCEL":
                    self.download_queue.task_done() 
                    continue
                if db_item is None:
                    self.download_queue.task_done() 
                    continue
                config = SupportKakaotv.make_wvtool_config(db_item.info)
                if config == None:
                    db_item.status = "NOT_SUPPORTED"
                    db_item.completed = True
                    db_item.completed_time = datetime.now()
                    db_item.save()
                else:
                    config['callback_id'] = f"{P.package_name}_{self.name}_{db_item.id}"
                    config['logger'] = P.logger
                    config['folder_tmp'] = os.path.join(F.config['path_data'], 'tmp')
                    config['folder_output'] = ToolUtil.make_path(P.ModelSetting.get(f"{self.name}_save_path"))
                    if P.ModelSetting.get_bool(f"{self.name}_make_program_folder"):
                        config['folder_output'] = os.path.join(config['folder_output'], db_item.info['channel_name'])
                    config['clean'] = True
                    downloader = SupportKakaotv.WVDownloaderKakao(config, callback_function=self.wvtool_callback_function)
                    downloader.start()
                    self.current_download_count += 1
                self.download_queue.task_done() 
            except Exception as e: 
                logger.error(f"Exception:{str(e)}")
                logger.error(traceback.format_exc())

    def db_delete(self, day):
        return ModelKakaotvProgram.delete_all(day=day)

    def retry_download_failed(self):
        failed_list = ModelKakaotvProgram.get_failed()
        for item in failed_list:
            item.init_for_queue()
            self.download_queue.put(item)
        return len(failed_list)


    def wvtool_callback_function(self, args):
        try:
            db_item = ModelKakaotvProgram.get_by_id_in_queue(args['data']['callback_id'].split('_')[-1])
            if db_item is None:
                return
            is_last = True

            if args['status'] in ["READY", "SEGMENT_FAIL"]:
                is_last = False
            elif args['status'] == "EXIST_OUTPUT_FILEPATH":
                pass
            elif args['status'] == 'USER_STOP':
                pass
            elif args['status'] == "COMPLETED":
                pass
            elif args['status'] == "DOWNLOADING":
                is_last = False
            
            db_item.status = args['status']
            if is_last:
                self.current_download_count += -1
                db_item.completed = True
                db_item.completed_time = datetime.now()
                db_item.save()

            self.socketio_callback('status', db_item.as_dict())
        except Exception as e: 
            P.logger.error(f'Exception:{str(e)}')
            P.logger.error(traceback.format_exc())


    ######################################################################

    





class ModelKakaotvProgram(ModelBase):
    P = P
    __tablename__ = f'{P.package_name}_program'
    __table_args__ = {'mysql_collate': 'utf8_general_ci'}
    __bind_key__ = P.package_name

    id = db.Column(db.Integer, primary_key=True)
    created_time    = db.Column(db.DateTime)
    completed_time  = db.Column(db.DateTime)
    completed       = db.Column(db.Boolean)
    
    clip_id = db.Column(db.String)
    info = db.Column(db.JSON)
    status = db.Column(db.String)
    call = db.Column(db.String)
    queue_list = []


    def __init__(self, clip_id, info, call='user'):
        self.clip_id = clip_id
        self.info = info
        self.completed      = False 
        self.created_time = datetime.now()
        self.status = "READY"
        self.call = call
        

    def init_for_queue(self):
        self.status = "READY"
        self.queue_list.append(self)


    @classmethod
    def get(cls, clip_id):
        with F.app.app_context():
            return db.session.query(cls).filter_by(
                clip_id=clip_id,
            ).order_by(desc(cls.id)).first()


    @classmethod
    def is_duplicate(cls, clip_id):
        return (cls.get(clip_id) != None)


    # 오버라이딩
    @classmethod
    def make_query(cls, req, order='desc', search='', option1='all', option2='all'):
        with F.app.app_context():
            query = F.db.session.query(cls)
            #query = cls.make_query_search(query, search, cls.program_title)
            query = query.filter(cls.info['channel_name'].like('%'+search+'%'))
            if option1 == 'completed':
                query = query.filter_by(completed=True)
            elif option1 == 'incompleted':
                query = query.filter_by(completed=False)
            elif option1 == 'auto':
                query = query.filter_by(call="user")

            if order == 'desc':
                query = query.order_by(desc(cls.id))
            else:
                query = query.order_by(cls.id)
            return query 


    @classmethod
    def remove_all(cls, is_completed=True): # to remove_all(True/False)
        with F.app.app_context():
            count = db.session.query(cls).filter_by(completed=is_completed).delete()
            db.session.commit()
            return count

    @classmethod
    def get_failed(cls):
        with F.app.app_context():
            return db.session.query(cls).filter_by(
                completed=False
            ).all()
        

    ### only for queue
    @classmethod
    def get_by_id_in_queue(cls, id):
        for _ in cls.queue_list:
            if _.id == int(id):
                return _
    ### only for queue END
