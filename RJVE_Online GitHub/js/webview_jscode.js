   // 操作逻辑略.....
   video.play();
   //设置画面比例，确保切换源时为选择的画面比例
   setscale(ku9.getscale());

   // 画面比例控制，app通过画面比例设置，切换scaletype值切换不同比例，注：function setscale(scaletype)为全局函数
   function setscale(scaletype) {
              switch (scaletype) {
                  case 0: // 默认
                      //执行代码
                      break;

                  case 1: // 16:9
                      //执行代码
                      break;

                  case 2: // 4:3
                      //执行代码
                      break;

                  case 3: // 填充
                      //执行代码
                      break;

                  case 4: // 原始
                      //执行代码
                      break;

                  case 5: // 裁剪
                      //执行代码
                      break;
              }
          }


   //指定视频时长（duration>0时，播放视频时app界面左右滑动弹出seekbar，单位秒）
   ku9.setduration(duration)

   //指定视频进度（播放视频时跳转指定时长）
   ku9.setposition(position)

   //视频暂停（app界面左右滑动弹出seekbar后，按暂停按钮执行此方法让视频暂停）
   function pause() {
    //执行代码
  }

   //视频播放（app界面左右滑动弹出seekbar后，按播放按钮执行此方法让视频播放）
   function play() {
    //执行代码
   }

   //拖动视频进度时（app界面左右滑动弹出seekbar后，移动seekbar执行此方法让视频跳转至position位置播放，单位秒）
  function setposition(position) {
    //执行代码
   }

   //视频倍速（app界面左右滑动弹出seekbar后，实现点击倍速按钮切换视频播放速度，长按恢复倍速功能）
   function setspeed(float){
   //执行代码（接收float类型的倍速值，设置视频倍速，如：video.playbackRate = float）
   }

