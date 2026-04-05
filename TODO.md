- [x] Add User agent property https://github.com/NotJoeMartinez/yt-fts/blob/7fbc0088f30672b6fbfe2ea7351fa42bafe1f886/src/yt_fts/download/download_handler.py#L562  
My suggestion for your next Cursor prompt:

"Refine my ingest.py by incorporating two features from ytb-fts:

Add a list of 10 common User-Agents and have yt_dlp pick one at random for each request.

Update the channel sync to check both the /videos and /streams tabs of the channel URL so I don't miss any content."
- [ ] Impersonate the api calls
- [x] Add the error handling during download and added error download to the registry database
- [ ] Create per channel per db file, and figure out data management for tables
- [X] Set LLM_PROVIDER=ollama in config 
- [x] Update the title time information in cards like this 发布时间: 04/02/2026
时长: 2:25:15
播放量: -
会员: subscriber_only
类型: streams
直播状态: completed
- [ ] Ask user and confirm the config of model usage in transcribeing, preprocessing cleaning text, summarizing and answering questions, chunking embedding choice and change the code base accodingly 
- [ ] sync channel Trade-off
但这里也有一个现实问题：
video_exists(conn, vid) 只是检查 DB 是否已有 video_id
它不检查本地 mp3 是否还在
也不检查该行是不是 error 状态、坏记录、半成品记录
所以当前逻辑更像：
> “只要这条 DB 记录存在，就认为这个视频已经 ingest 过了。”
这对正常使用是够的，但如果你以后想更稳，可以把跳过逻辑改成检查：
video_id exists
且 download_status == downloaded
且 mp3_path 文件存在
否则就重新下载。
- [x] elegant cli design