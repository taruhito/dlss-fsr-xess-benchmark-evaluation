論文題目

「即時渲染中超解析度之三大升頻軟體 DLSS、FSR 與 XeSS 的標準化測試流程與比較研究」




研究目的


建立可重複、客觀的標準化測試流程與訂定評估指標，為遊戲或應用程式開發者提供便利的實測及評估方法。
系統性比較與綜合分析 NVIDIA DLSS、AMD FSR、Intel XeSS 三者在不同類型遊戲應用中：系統資源占用 (CPU、GPU / VRAM)、全機耗電量 (Watt)、影格速率表現 (FPS、frame time)、大略的個人電腦延遲 (Approximate PC Latency)、畫質解析度表現 (PSNR、SSIM、MS SSIM、LPIPS、DISTS)，為遊戲玩家或開發者提供選型建議。




研究方法


測試平台

 硬體
筆電：ASUS ROG Zephyrus G14
	CPU：AMD Ryzen 9 7940HS（4.00 GHz）
	GPU：NVIDIA GeForce RTX 4080 12 GB
	記憶體：32 GB DDR5
	磁碟：Samsung MZVL21T0HCLR SSD NVMe PCIe 4.0


軟體
作業系統：Windows 11 Pro
	顯卡驅動程式：NVIDIA Game Ready Driver ≥ 580.XX
	圖形 API：DirectX 12 / Vulkan




測量儀器與工具


系統資源占用 / 影格速率表現
工具：HWiNFO + RTSS
• 透過啟用 RTSS 擷取詳細的 FPS、1% Low、0.1% Low、frametime 等影格速率表現
• HWiNFO 記錄 CPU / GPU 利用率、VRAM 使用量、溫度等感測器數據
• 匯出 csv log，可進一步分析、搭配 Python 腳本處理及視覺化


全機耗電量
儀器：AC 電量分析儀 BENETECH GM89
• 直接量測筆電 AC 端的整體耗電 (Watt)
• 架設手機錄下螢幕瓦特讀數，後續逐秒擷取數值紀錄 csv log，搭配 Python 腳本處理及視覺化


大略的個人電腦延遲
工具：OCAT
• 指標：PC Latency (approximate) = Game Latency (partial) + Render Latency
• 匯出 csv log，進一步分析並搭配 Python 腳本處理及視覺化
• 不採用：高速攝影機 (高價)、NVIDIA LDAT (需外接的感應器購買困難，且線上自製感應器教學針對滑鼠的延遲測試，無對應本研究採用之手把測試)


畫質解析度表現
工具：遊戲內拍照模式 or NVIDIA App (ALT+F1) + FR-IQA 
• 指標：FR-IQA (PSNR、SSIM、MS SSIM、LPIPS、DISTS)
• 使用遊戲內預設拍照模式截圖，或透過 NVIDIA App 截圖遊戲畫面原畫質，確保盡量截圖相同影格、尺寸、視角、光源與場景參數，並作正規化，再搭配 Python 腳本計算 FR-IQA 指標分數，最後視覺化結果
• 不採用 NR-IQA (應用於遊戲升頻量測上不準確)




測試場景

商業遊戲
挑選近年 5 款同時支援 DLSS、FSR、XeSS 的不同類型遊戲，包含需要低延遲的格鬥遊戲、需要大量資源的開放式世界遊戲、動作遊戲、需求高影格數的第一人稱射擊遊戲：
– 《VR快打5 R.E.V.O.》、《光與影：33號遠征隊》、《對馬戰鬼 導演剪輯版》、《浩劫殺陣2：車諾比之心》、《沉默之丘2》


解析度與升頻模式
解析度：
1080p (1920*1080) - common baseline
2.5k / WQXGA (2560*1600) - laptop’s native highest-res panel
升頻模式：
《Virtua Fighter 5 R.E.V.O.》
modes selected： Base、NVIDIA Reflex Boost (maximum latency reduction)
sr modes selected：
DLSS（品質、平衡、超高效能)
FSR 1（超高品質、平衡、效能)
FSR 3.1.2 (品質、平衡、超高效能)
XeSS（超高品質 Plus、平衡、超高效能)


total tests：2(res)*2(modes)*4(sr)*3(sr modes) = 48 tests
	
	《光與影：33號遠征隊》
		由於此遊戲未提供完全關閉 upscalers 的選項，而本研究使用 NVIDIA GPU，因此採用最接近原生解析度的抗鋸齒模式 DLAA (未經升頻) 作為原始參考影格之取樣模式，用以配合後續 FR-IQA 指標評估。
modes selected：Base、NVIDIA Reflex Boost、NVIDIA Frame Generation 2X (Reflex Boost)
sr modes selected：
DLSS（品質、平衡、卓越性能)
FSR （品質、平衡、效能)
XeSS（超高品質、平衡、卓越性能)




實驗流程

訂定電腦閒置狀態基線 (測出背景程式占用資源、雜訊)


重啟電腦，確保所有非必要軟體關閉，停用 / 結束非必要之背景程式服務 (此為定義閒置狀態基線，因此不必停用所有服務 / 程式，只需結束較耗資源的程式以免妨礙遊戲運行)
啟用 RTSS 再運行 HWiNFO 感應器模式 (Sensor Only Mode)，打開 OCAT，接上 BENETECH GM89，並閒置三分鐘
手機錄製 BENETECH GM89，並點擊重設、錄製 HWiNFO 共 1 分鐘作為閒置狀態之所耗資源、電量基線 (遊戲有 DRM 故 Steam 會保持開啟，視為遊戲運行資源)
啟動遊戲，分別在 1080p / 2.5k 解析度選擇不同欲測試之畫面影格 (盡量選擇不同類型影格截圖，包括動作場景、物件眾多場景、遠景等)，等待至 TAA 穩定後，以拍照模式或以 ALT + F1 啟動 NVIDIA App 各截圖 10 次 (重新載入遊戲、重播以重回到該影格 / 動作 / 畫面，為該影格重複 10 次微異同畫面之截圖，10 screenshots per frame)，以便後續轉換為 RGB 浮點數陣列正規化後，取其中位數作為未升頻之原始參考影格數據 (以避免頭髮、衣物或是背景效果等雜訊影響 FR-IQA 指標分數)。截圖取樣時，善用遊戲內的設定確保取樣的一致性，比如格鬥遊戲的 frame by frame 重播功能、動作遊戲拍照模式可關閉物件及角色等等。


測試不同模式並記錄 (截圖取樣步驟可獨立出來)


包含初次的每一次測試開始前，設定好解析度與測試模式預備，待機一分鐘等待系統穩定 (觀察 BENETECH GM89 之瓦數，如果未穩定下來再等待 1 分鐘，若依然波動起伏大則重作步驟一，省略錄製基線、截圖動作)
手機錄製 BENETECH GM89，點擊重設、錄製 HWiNFO，按 F10 開始錄製 OCAT，開始跑遊戲測試情境 (以動作、複雜情境為主，並利用重播功能，若無則盡量貼近每次情境) 至 OCAT 設定好一分鐘後自動停止，再停止錄製 HWiNFO、BENETECH GM89 之錄影
選擇 / 移動至不同欲測試之畫面影格，等待 TAA 穩定後，為不同影格各截圖取樣 3 次 (詳細步驟參考步驟一)
檢查所有紀錄與截圖，完成後關閉
重複 a ~ d 之流程直到所有的解析度與模式測試完畢


Python 腳本計算結果並視覺化


Hardware (HWiNFO)
提取完整後 60 秒之紀錄，計算指標 (original metrics) 為：
GPU 功率 [W]：GPU 當下的總體耗電功率 (瓦特)。
CPU 封裝功率 [W]：CPU晶片封裝內的總體電能消耗，指中央處理器在運行時所消耗的總電力 (瓦特)。
GPU 核心使用率 [%]：指顯示卡在處理任務時的忙碌程度。
顯示記憶體控制器使用率 [%]：GPU 上的專用記憶體被占用的比例，高使用率表示遊戲或應用程式需要像高解析度紋理等大量圖形資料，可能影響效能，導致畫面卡頓。
GPU 有效頻率 [MHz]：GPU 在實際工作負載下的有效運作時脈，顯示 GPU 真正投入運算的平均強度，影響時脈駐留 (clock residency)、動態電壓頻率調整 (DVFS) 與閒置時間等。
GPU D3D 專用顯示記憶體 [MB]：Direct3D 報告的專用 VRAM 實際占用量，代表遊戲或應用程式目前在顯示卡專用記憶體中配置並使用的資源，若接近顯卡 VRAM 上限可能會導致效能下降。
CPU 總使用率 [%]：CPU 全核心的平均忙碌比例、整體使用率，用於表示 CPU 端的工作負載與瓶頸情況。
影格率 [FPS]：Frames Per Second，每秒畫面產生並呈現的影格數量，也稱幀數、畫面更新率。
1% 低影格率 [FPS]：測試期間每次取樣時刻的即時 FPS 中表現最差的 1% 區段之代表值 (透過 RTSS 內部統計方法即時計算的低尾端 FPS)，用來衡量短暫卡頓與流暢度穩定性。
0.1% 低影格率 [FPS]：測試期間表現最差的 0.1% 區段之 FPS，更強調尾端 (體感極短暫突然一頓) 的卡頓與掉幀情況。
影格時間 [ms]：指影格被渲染、產出的時間間隔 (約為 1000 ms (1秒) / FPS)，反映產出端的產出速度 (throughput)。
Frame Time Presented (avg) [ms]：影格實際被呈現到顯示管線的平均時間間隔，描述呈現端的畫面更新節奏 (frame pacing)，會受到 VSync、佇列、合成器等呈現路徑因素影響。
記憶體頻率 [MHz]：衡量 RAM 運行速度的指標，表示在特定時間內能夠傳輸的資料量，頻率越高資料傳輸速度越快，電腦效能也越好。
評估指標 (derived metrics)：
占用資源排序鍵：透過計算減去 ”取中位數之閒置狀態基線功耗” 的 GPU 功率 + CPU 封裝功率陣列，並取其平均值，得真實 CPU + GPU 平均功率，以作為主要排序依據。
占用資源次排序鍵：分別將 GPU 核心使用率、顯示記憶體控制器使用率、GPU 有效頻率、GPU D3D 專用顯示記憶體、CPU 總使用率陣列，各取其平均值並全部正規化至 [0,1] 區間，各賦予權重 (GPU 相關較高，依序：0.32, 0.22, 0.2, 0.16, 0.1; total=1)，計算正規化數值*權重，再加總作為若主要排序相同時，採用的次要排序依據。
FPS 表現排序鍵：以 60 秒的平均影格率作為主要排序依據，若平均 FPS 全部一致時，採計算詳細 FPS 表現分數之公式：(1*平均 1% 低影格率 + 1.3 (略為強調 0.1% 的表現)*平均 0.1% 低影格率) / (1 + 1.3) 所得 FPS 分數作為主要排序依據。
FPS 表現次排序鍵：若主要排序重疊，使用平均影格率為主排序鍵時，其後依序採詳細 FPS 表現分數 (如上定義)、平均影格時間、平均 Frame Time Presented (avg)、平均 0.1% 低影格率、平均 1% 低影格率作為次排序鍵；使用詳細 FPS 表現分數為主排序鍵時，其後依序採平均影格時間、平均 Frame Time Presented (avg)、平均 0.1% 低影格率、平均 1% 低影格率作為次排序鍵。
		視覺化結果：
各模式解析度占用資源排序：以占用資源排序鍵及次排序鍵建構長條圖。
真實所耗平均 CPU + GPU 排序：以占用資源排序鍵及次排序鍵建構長條圖，分別顯示平均 CPU、GPU 功耗。
整體 upscalers 占用資源排序：為各 upscaler 所有解析度、模式的真實 CPU + GPU 平均功率取一個中位數，排序建構長條圖。
各模式解析度 FPS 表現分數排序：以FPS 表現排序鍵及次排序鍵建構長條圖。
平均 1% 低影格率 + 0.1% 低影格率排序：以FPS 表現排序鍵及次排序鍵建構長條圖，分別顯示平均 1% 低影格率、0.1% 低影格率之 FPS。
整體 upscalers FPS 表現分數排序：為各 upscaler 所有解析度、模式的平均影格率取一個平均值 (或取平均 1% 低影格率、平均 0.1% 低影格率之平均值，再套用計算詳細 FPS 表現分數之公式)，排序建構長條圖。
整體 upscalers 硬體層面綜合排序：以各個 upscaler 的平均影格率 (或詳細 FPS 表現分數) / 其真實 CPU + GPU 平均功率中位數，計算出每一功率所帶來的 FPS 表現，建構整體綜合排序長條圖。
資源 vs FPS 散布圖：分別建構各 upscalers 所有解析度、模式的真實 CPU + GPU 平均功耗，對應其平均影格率 (或詳細 FPS 表現分數)、平均 1% 低影格率、平均 0.1% 低影格率之共三張散布圖。
記憶體頻率飄移長條圖：檢查測試期間各解析度、模式之記憶體頻率是否有產生漂移的長條圖，若其最大、最小值相差 > 10 MHz 即有飄移。
Watt：
將對 BENETECH GM89 的手機錄影快轉至 OCAT 所記錄詳細開始錄製時間，每秒紀錄一次當下瓦數，共紀錄 60 次以建立所耗瓦數紀錄，計算指標為：
原始瓦數 [W]：透過 BENETECH GM89 直接量測筆電 AC 端所得全機耗電量。
		評估指標：
實際平均消耗瓦數：透過計算減去 ”取中位數之閒置狀態基線瓦數” 的原始瓦數陣列，並取其平均值，得實際平均消耗瓦數，以作為排序依據。
每影格實際消耗焦耳：透過計算減去 ”取中位數之閒置狀態基線瓦數” 的原始瓦數陣列，並將其加總，得 60 秒之實際能量焦耳，再將其 / 平均影格率 (自 Hardware 評估指標)*60 秒，計算出單一影格所耗焦耳，以作為排序依據。
		視覺化結果：
實際平均消耗瓦數排序：以實際平均消耗瓦數排序建構長條圖。
每影格實際消耗焦耳排序：以單一影格所耗焦耳排序建構長條圖。
整體 upscalers 消耗瓦數排序：為各 upscaler 所有解析度、模式的實際平均消耗瓦數取一個中位數，排序建構長條圖。
Latency (OCAT)：
提取完整紀錄 (已定時一分鐘之自動錄製與停止)，計算指標為：
MsInPresentAPI：屬於個人電腦延遲 (PC Latency) 的遊戲延遲 (Game Latency) 內一部分，發生於渲染提交 (Render Submission) 至驅動程式期間。指 CPU 呼叫 Present() 函式直到其返回 (Return) 時，等待 VSync (註*) 阻塞與隊列壓力 (Queue Back-pressure) 等所花費的時間，衡量 CPU 在輸出階段被擋住多久。
MsEstimatedDriverLag：屬於個人電腦延遲的渲染延遲 (Render Latency) 前半部分，指驅動程式排隊等候渲染隊列 (Render Queue) 的延遲，估計已提交的影格 (submitted frame：CPU 已處理完畢並發送給顯卡之影格) 在 GPU 實際開始處理前於渲染隊列中停留的時間。
MsUntilRenderComplete：屬於個人電腦延遲的渲染延遲後半部分，指影格被 GPU 實際開始處理到完成渲染的時間。
執行階段 (Graphics API)：圖形應用程式介面之執行階段，常見 API 包含 DirectX、OpenGL、Vulkan，作為軟體與 GPU 間的橋樑，負責告訴硬體如何渲染 3D 畫面。
同步間隔 (SyncInterval)：輸出 0 表示 VSync (註*) 未啟用或 VRR (Variable Refresh Rate：G-Sync、FreeSync)；1 表示啟用 VSync。
*垂直同步 (VSync)：透過限制顯卡幀率輸出，使其與顯示器之刷新週期對齊，彼此同步以消除畫面撕裂現象，確保顯示影像流暢穩定，但同時可能增加輸入延遲並降低遊戲效能。在競技類遊戲中，玩家通常會關閉 VSync。
GPU #：GPU number，顯示使用電腦的第幾個 GPU。
GPU：圖形處理器，由數百至數千個小型核心組成，能高效處理圖形任務和大量平行運算，而以 GPU 為核心的主機板擴充卡稱為顯示卡。
處理器 (CPU)：此指中央處理器 CPU，為電腦的大腦，負責執行指令、處理數據與控制運算。
主機板：電腦的核心元件，用於連接 CPU、顯示卡、記憶體、磁碟等硬體。
作業系統：使用者與硬體之間的橋樑，提供人機互動介面，讓使用者能執行應用程式，電腦常見的 OS 有 Windows、MacOS、Linux 等。
記憶體：泛指 RAM，用於臨時儲存資料和程式，以便 CPU 可以快速存取。
		評估指標：
平均大略個人電腦延遲 (Approximate PC Latency Mean)：透過將部分遊戲延遲 (MsInPresentAPI) 陣列 + 渲染延遲 (MsEstimatedDriverLag + MsUntilRenderComplete) 陣列，並取其平均值，以計算出平均大略個人電腦延遲，作為主要排序依據，而平均渲染延遲、平均部分遊戲延遲則依序作為次要排序。
一致性驗證：透過 OCAT 取得執行階段、同步間隔、GPU #、GPU、處理器、主機板、作業系統、記憶體資訊陣列，檢查確保測試途中保持一致性，證明結果的公正性及可信度，若檢查指標有異動則列出，嚴重至可影響實驗解果則重測。
		視覺化結果：
平均大略個人電腦延遲排序：以平均大略個人電腦延遲為主排序鍵，平均渲染延遲、平均部分遊戲延遲作為次排序鍵建構長條圖，並附上一次性驗證資料。
平均大略個人電腦延遲成員排序：同平均大略個人電腦延遲排序長條圖，分別顯示平均渲染延遲、平均部分遊戲延遲時間，並附上一次性驗證資料。
平均渲染延遲成員排序：以平均渲染延遲排序建構長條圖，分別顯示平均 MsEstimatedDriverLag、平均 MsUntilRenderComplete，並附上一次性驗證資料。
整體 upscalers 延遲時間排序：為各 upscaler 所有解析度、模式的平均大略個人電腦延遲取一個中位數，排序建構長條圖，並附上一次性驗證資料。
Resolution：
確認清點所有擷取螢幕畫面，使用 FR-IQA (全參考圖像質量評估) 指標計算、評估原始影格 vs 升頻後的影格品質：
PSNR (峰值訊噪比，Peak Signal-to-Noise Ratio)：表示訊號最大可能功率，與影響其表示精度的破壞性雜訊功率之比值，單位為分貝 (dB)，而在影像處理上可透過計算原始訊號 (原始、參考影像) 和失真訊號 (壓縮、處理後的影像) 之分貝差異做為評估指標，若值越高表示失真越小、影像品質越好。其為像素的絕對誤差，與人眼辨識結果不一定一致，公式為兩個 m*n 的單色圖像 I (原始) 和 K (壓縮)，均方誤差定義為：

再透過訊號最大可能功率 (MAXI) 與均方誤差計算 PSNR：

MAXI 在影像處理中每個採樣點以 8-bit 灰階表是，故為 255，整體公式簡單定義為：10 * log10(255^2 / MSE(upscaled, ref))。
SSIM (結構相似性，Structural Similarity)：透過亮度、對比度、結構來衡量原影像與失真後影像彼此相似度，以評估失真影像的品質。其為結構的相似度，貼近人眼對影像品質的判斷，計算 x、y 結構相似性，公式定義為：

α, β, γ 為參數，C 為常數，計算組合三個相似性度量：light(x,y 平均值)、contrast(x,y 標準差)、structure(x,y 協方差) 加權，可得 [0,1] 區間之值，值越接近 1 表示相似性、品質越高。
MS-SSIM (多尺度結構相似性，Multi-Scale Structural Similarity)：相較於結構相似性使用特定大小的視窗進行計算，其採將輸入圖片經過多次低通濾波器與兩倍下採樣，每次下採樣後都計算一次結構相似度 (在不同解析度 / 尺度下計算)，故能有效評估不同解析度的圖片、更具準確性、也更貼近人眼對影像細節的判斷，值同樣越接近 1 表示品質越高。
LPIPS (Learned Perceptual Image Patch Similarity)：透過訓練好的深度學習模型 (如 VGG、AlexNet) 來提取圖像間特徵並計算距離，以衡量彼此的感知相似度。相較於傳統圖像評估指標 (PSNR、SSIM) 更貼近人眼感知方式，利用深度神經網路可捕捉到高層次的結構與內容，且 LPIPS 是計算圖像中不同區域之距離而非整張圖像，因此感知度更加敏感 (可捕捉微小差異)，常用於評估生成模型輸出品質，LPIPS 值普遍為 [0,1] 區間，值越低表示相似度越高。
DISTS (深度圖像結構與紋理相似性，Deep Image Structure and Texture Similarity)：使用深度神經網路提取特徵，計算圖片間的結構及紋理距離，相較於傳統圖像評估指標更貼近人眼判別方式，對輕微幾何變化極具敏感性，DISTS 值普遍為 [0,1] 區間，值越低表示相似度越高。
		視覺化結果：
各指標評估結果排序：將所有未升頻的原始參考影格轉換為 RGB 浮點數陣列，再將每測試畫面之影格 (10 個浮點數) 取一個中位數作為原始參考值，並計算經不同 upscalers 升頻後的測試畫面之影格 (同方式處理，取 3 個浮點數中位數) 的各項畫質評估指標，取各解析度、模式的所有測試畫面之影格評估值的平均後，依指標分數分別排序建構長條圖。
啟用模式與各指標評估結果解析圖：計算 (啟用模式 - 未啟用) 之同解析度、SR 模式的所有測試畫面影格中位數 (PSNR、SSIM、MS-SSIM)；(未啟用 - 啟用) 之同解析度、SR 模式的所有測試畫面影格中位數 (LPIPS、DISTS)，並為該解析度、模式取一個平均值，排序建構分向長條圖 (Diverging Bar Chart)，平均值越大表示啟用該模式時畫面品質越高，越低越差，0 則為中線表示不變。




附註


Structure


論文章節架構
緒論（研究動機、目的與範圍）
文獻回顧（DLSS、FSR、XeSS 原理、前人評測）
研究方法（測試平台、場景設定、量測流程與工具）
實驗結果（效能、資源、品質、延遲多維度分析）
結論與未來展望（最佳實務、後續可延伸方向）




Latency components




Resolution Screenshots Captures

Let σ_SR be the SD (standard deviation) of a single SR capture’s metric for a fixed frame.

Mean of n repeats: SD ≈ σ_SR / √n
Median of n repeats: SD ≈ 1.253 * σ_SR / √n (slightly less efficient, more robust)
Improvement factors relative to a single capture (median): n=1: 1.000 (baseline) n=2: 1.253 / √2 ≈ 0.887 (≈1.13× reduction) n=3: 1.253 / √3 ≈ 0.724 (≈1.38× reduction) n=4: 1.253 / 2 = 0.627 (≈1.59× reduction) n=5: 1.253 / √5 ≈ 0.561 (≈1.78× reduction)

So going from 1→3 gives most of the “robustness against a single bad capture” benefit; 3→5 adds only a modest further tightening. (very not likely 2 bad screenshots)

conceptually:

σ_SR is about raw single measurements.
When combine n measurements (mean or median), you get an ESTIMATOR whose variability (its own standard deviation) is smaller; that’s called its standard error (SE).

“Remaining variability fraction” after taking a median of n = 1.253/√n (approx).
“Improvement (reduction) factor” = 1 / (1.253/√n) = √n / 1.253.
Example for n=3: Remaining fraction ≈ 0.724 → you have 72.4% of the original noise. Improvement factor ≈ 1 / 0.724 ≈ 1.38 → noise reduced by about 1.38× (i.e., new SE ≈ old SE / 1.38).

That’s what “≈1.38× reduction” means: your estimator’s wobble is 1/1.38 ≈ 72% of the single-capture wobble.



