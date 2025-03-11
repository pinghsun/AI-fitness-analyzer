import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import re
import os
import json
import anthropic
from io import BytesIO
from datetime import datetime

# import matplotlib.pyplot as plt

# plt.rcParams['font.family'] = ['Noto Sans CJK SC']  # 'SimHei'或 'Microsoft YaHei', 'Noto Sans CJK SC' 等
# # 如果SimHei字型無法使用，可以嘗試 'Arial Unicode MS' 或 'Heiti TC' 等
# # plt.rcParams['font.sans-serif'] = ['SimHei'] # 備用設定，如果font.family 無效
# # plt.rcParams['axes.unicode_minus'] = False  # 用來正常顯示負號，針對部分系統可能需要


# 設置頁面
st.set_page_config(page_title="體適能數據分析助手", layout="wide")
st.title("體適能數據分析助手")

# 側邊欄上傳檔案功能
with st.sidebar:
    st.header("上傳檔案")
    uploaded_files = st.file_uploader("上傳Excel檔案", type=["xlsx", "xls"], accept_multiple_files=True)
    
    if uploaded_files:
        st.success(f"已上傳 {len(uploaded_files)} 個檔案")
    
    # Claude API 設置
    st.header("Claude API 設置")
    api_key = st.text_input("Anthropic API Key", type="password")
    if api_key:
        st.success("API Key 已設置")
    else:
        st.warning("請輸入 API Key 以啟用高級分析能力")

# 從檔案名稱提取日期的函數
def extract_date_from_filename(filename):
    # 嘗試從檔案名稱匹配日期格式 (如 2023-01-15, 20230115, 2023_01_15)
    patterns = [
        r'(\d{4}-\d{1,2}-\d{1,2})',  # YYYY-MM-DD
        r'(\d{4}_\d{1,2}_\d{1,2})',  # YYYY_MM_DD
        r'(\d{8})',                   # YYYYMMDD
    ]
    
    for pattern in patterns:
        match = re.search(pattern, filename)
        if match:
            date_str = match.group(1)
            
            # 處理不同的日期格式
            try:
                if '-' in date_str:
                    return datetime.strptime(date_str, '%Y-%m-%d')
                elif '_' in date_str:
                    return datetime.strptime(date_str, '%Y_%m_%d')
                else:
                    return datetime.strptime(date_str, '%Y%m%d')
            except ValueError:
                pass
    
    # 如果沒有找到日期，則返回 None
    return None

# 全局變數存儲數據
data_frames = {}
combined_data = None
test_dates = {}

# 處理上傳的文件
if uploaded_files:
    for file in uploaded_files:
        try:
            # 讀取Excel
            df = pd.read_excel(file)
            
            # 獲取檔案名稱
            filename = file.name.split('.')[0]
            
            # 嘗試從檔案名稱提取日期
            test_date = extract_date_from_filename(filename)
            if test_date:
                # 如果找到日期，將其格式化為字符串作為識別符
                date_str = test_date.strftime('%Y-%m-%d')
                df['測試日期'] = date_str
                test_dates[filename] = date_str
            else:
                # 如果沒有找到日期，則直接使用檔案名稱
                df['測試日期'] = filename
                test_dates[filename] = filename
            
            # 檢查是否有學生ID或姓名列
            if not ('學生ID' in df.columns or '姓名' in df.columns):
                st.sidebar.warning(f"警告: 檔案 '{filename}' 缺少學生識別資訊 (學生ID 或 姓名)。")
            
            # 標準化列名稱（處理可能的差異）
            df.columns = [col.strip().lower() for col in df.columns]
            
            # 保存數據框
            data_frames[filename] = df
            
            st.sidebar.write(f"檔案 '{filename}' 已載入，包含 {len(df)} 筆記錄")
        except Exception as e:
            st.sidebar.error(f"無法讀取 {file.name}: {e}")
    
    # 顯示檢測到的測試日期
    if test_dates:
        st.sidebar.subheader("檢測到的測試日期:")
        for filename, date_str in test_dates.items():
            st.sidebar.write(f"{filename}: {date_str}")
    
    # 嘗試合併數據
    if len(data_frames) > 0:
        try:
            # 驗證所有數據框是否有共同的識別列
            id_columns = ['學生id', '姓名', 'id', '學號']
            common_id_col = None
            
            # 檢查所有數據框中是否有共同的識別列
            for col in id_columns:
                if all(col in df.columns for df in data_frames.values()):
                    common_id_col = col
                    break
            
            if common_id_col:
                # 合併所有數據框
                dfs_to_merge = []
                for name, df in data_frames.items():
                    df_copy = df.copy()
                    df_copy['數據來源'] = name
                    dfs_to_merge.append(df_copy)
                
                combined_data = pd.concat(dfs_to_merge, ignore_index=True)
                
                # 在session_state中保存合併的數據
                st.session_state['combined_data'] = combined_data
                st.session_state['common_id_col'] = common_id_col
                
                st.sidebar.success(f"所有數據已成功合併！使用 '{common_id_col}' 作為學生識別符。")
                
                # 顯示合併數據的基本資訊
                st.sidebar.write(f"合併數據包含 {len(combined_data)} 筆記錄")
                st.sidebar.write(f"可用於分析的測試日期: {', '.join(combined_data['測試日期'].unique())}")
            else:
                st.sidebar.warning("無法找到所有檔案共用的學生識別符列（如 '學生ID' 或 '姓名'）。請確保所有檔案具有相同的識別列。")
        except Exception as e:
            st.sidebar.error(f"合併數據時出錯: {str(e)}")

# 數據預覽
if combined_data is not None:
    with st.expander("預覽合併後的數據"):
        st.dataframe(combined_data)

# 問答區塊
st.header("數據分析問答")

# 定義預設問題範例
example_questions = [
    "本次跑步測試排行由高到低",
    "請以長條圖呈現學生各測試項目的表現在全班的百分比",
    "分析每位學生在不同測試日期的體適能進步情況",
    "比較兩次測試間仰臥起坐成績的進步情況"
]

# 創建問題輸入區，包含範例
question = st.text_input("請輸入您的問題:", 
                        placeholder="例如：本次跑步測試排行由高到低")

# 添加範例問題按鈕
st.write("或選擇範例問題:")
cols = st.columns(2)
for i, eq in enumerate(example_questions):
    if cols[i % 2].button(eq, key=f"example_{i}"):
        question = eq
        # 使用參數重新運行應用來更新text_input
        st.experimental_rerun()

# 使用 Claude API 處理問題
def ask_claude(question, data_sample, api_key):
    client = anthropic.Anthropic(api_key=api_key)
    
    # 獲取測試日期列表（從早到晚排序）
    test_dates_list = sorted(data_sample['測試日期'].unique())
    
    # 準備數據樣本，轉換為易於AI理解的格式
    data_json = data_sample.to_json(orient='records', force_ascii=False)
    
    prompt = f"""
    我需要你分析一些體適能測試數據並回答問題。
    
    數據樣本：
    ```json
    {data_json}
    ```
    
    可用的列名: {', '.join(data_sample.columns.tolist())}
    可用的測試日期: {', '.join(test_dates_list)}
    
    問題：{question}
    
    請根據數據提供詳細分析並說明如何處理這些數據才能回答問題。
    如果需要繪製圖表，請直接生成python程式碼，不需要做解釋。
    
    如果問題涉及比較不同測試日期之間的進步情況，請特別注意使用'測試日期'列來分組和比較數據。
    
    回答格式應該包含兩部分：
    1. 分析結果：依據問題生成表格，再根據表格回答問題 (重要：務必有表格說明)
    2. 數據處理：圖形需求使用Streamlit 專為 DataFrame 設計的 st.line_chart() st.bar_chart() st.area_chart() st.scatter_chart()函式，數據使用data_sample所存放的資料（格式為Pandas DataFrame），產生的程式碼須包含sort_values('測試日期')

    生成圖形範例程式：
    # 問題為王小明表現以折線圖表示
    import pandas as pd
import streamlit as st

# 將數據加載到DataFrame中
combined_data = pd.DataFrame(data)

# 找到王小明的數據
wang_xiaoming = combined_data[combined_data['姓名'] == '王小明']

# 顯示王小明的測試結果
st.title("王小明的體適能測試結果")
st.write(wang_xiaoming)

# 繪製王小明各項測試指標的變化趨勢
st.title("王小明各項測試指標的變化趨勢")

# 50公尺跑步時間
st.subheader("50公尺跑步時間")
st.line_chart(wang_xiaoming['50公尺跑步(秒)'])

# 仰臥起坐次數
st.subheader("仰臥起坐次數")
st.line_chart(wang_xiaoming['仰臥起坐(次)'])

# 坐姿體前彎
st.subheader("坐姿體前彎")
st.line_chart(wang_xiaoming['坐姿體前彎(公分)'])

# 立定跳遠
st.subheader("立定跳遠")
st.line_chart(wang_xiaoming['立定跳遠(公分)'])

    """
# 如果需要繪製圖表，請說明應該使用什麼類型的圖表，以及應該選擇哪些數據列進行繪製。
# //////////////////////////
# 2. 數據處理步驟：使用Python代碼說明如何處理數據，直接根據代碼內容生成結果呈現 
#     ，詳細步驟如下：
    
    
# 使用 Streamlit 框架和 Matplotlib 函式庫，根據體測數據繪製圖型。

# 我的體測數據存儲在一個 Python 列表 `data_sample` 中。`data_sample` 是一個列表 of 字典 (list of dictionaries)。
# 每個字典代表一筆體測記錄，包含以下鍵：'姓名', '測試日期', '50公尺跑步(秒)', '仰臥起坐(次)', '坐姿體前彎(公分)', '立定跳遠(公分)'。

# 資料範例：
# [
#     {'姓名': '王小明', '測試日期': '2023-01-01', '50公尺跑步(秒)': 8.5, '仰臥起坐(次)': 25, '坐姿體前彎(公分)': 15, '立定跳遠(公分)': 180},
#     {'姓名': '王小明', '測試日期': '2023-02-01', '50公尺跑步(秒)': 8.3, '仰臥起坐(次)': 28, '坐姿體前彎(公分)': 16, '立定跳遠(公分)': 185},
#     ...
# ]

# 程式碼需要完成以下步驟：

# 1.  首先，使用列表推導式從 `data_sample` 中篩選出 '姓名' 為 '王小明' 的所有記錄，並將篩選結果儲存在一個新的列表 `wang_data` 中。
# 2.  使用 Matplotlib 的 `pyplot` 模組創建一個折線圖。
# 3.  折線圖的 x 軸應該是 '測試日期'。
# 4.  折線圖需要繪製四條折線，分別代表以下四個體測項目：'50公尺跑步(秒)', '仰臥起坐(次)', '坐姿體前彎(公分)', '立定跳遠(公分)'。
# 5.  對於每個體測項目，使用列表推導式從 `wang_data` 中提取對應的成績數據作為 y 軸資料。
# 6.  為每條折線添加圖例 (label)，清楚標示代表的體測項目。
# 7.  設定 x 軸標題為 '測試日期'，y 軸標題為 '成績'。
# 8.  最後，使用 `streamlit.pyplot(fig)` 將生成的 Matplotlib 圖表顯示在 Streamlit 應用程式中。

# 請生成完整的 Python 程式碼。
    
    
    try:
        response = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=2000,
            temperature=0,
            system="你是一個體適能數據分析專家，協助教師解析學生的體適能測試數據。你擅長比較不同測試日期之間的進步情況和數據可視化。",
            messages=[{"role": "user", "content": prompt}]
        )
        
        return response.content[0].text
    except Exception as e:
        return f"Claude API調用失敗: {str(e)}"

# 處理問題邏輯
if question and combined_data is not None:
    st.write(f"分析問題: **{question}**")
    
    # 使用 Claude API 進行數據分析
    if api_key:
        try:
            with st.spinner("正在使用AI進行深度分析..."):
                # 使用完整數據集進行分析
                data_sample = combined_data
                claude_response = ask_claude(question, data_sample, api_key)
                
                # 顯示Claude分析結果
                st.subheader("分析結果")
                st.write(claude_response)
                
                # 尋找Claude回答中的Python代碼
                code_pattern = r'```python(.*?)```'
                code_match = re.search(code_pattern, claude_response, re.DOTALL)
                
                if code_match:
                    code = code_match.group(1).strip()
                    st.subheader("執行代碼")
                    
                    with st.expander("查看代碼"):
                        st.code(code, language="python")
                    
                    # 創建一個代碼執行按鈕
                    if st.button("執行Claude建議的分析代碼"):
                        try:
                            # 準備執行環境
                            local_vars = {
                                "data": combined_data,  # 使用變數名data
                                "combined_data": combined_data,
                                "pd": pd,
                                "plt": plt,
                                "sns": sns,
                                "np": __import__("numpy"),
                                "st": st
                            }
                            
                            # 執行代碼
                            exec(code, globals(), local_vars)
                            st.success("分析代碼已成功執行")
                        except Exception as e:
                            st.error(f"執行代碼時出錯: {str(e)}")
                            st.error(f"詳細錯誤信息: {str(e)}")
        except Exception as e:
            st.error(f"使用Claude API時出錯: {str(e)}")
    else:
        st.warning("請輸入API Key以啟用數據分析能力。所有分析都將使用Claude AI進行處理。")

# 如果沒有上傳檔案，顯示說明
if not uploaded_files:
    st.info("請在側邊欄上傳Excel檔案以開始分析。")
    
    # 顯示示例數據結構
    st.subheader("預期數據格式示例:")
    
    # 創建示例數據
    example_data = pd.DataFrame({
        '學生ID': [1001, 1002, 1003, 1004, 1005],
        '姓名': ['王小明', '李小華', '張小美', '陳小剛', '林小雯'],
        '班級': ['A班', 'A班', 'B班', 'B班', 'A班'],
        '50公尺跑(秒)': [7.8, 8.2, 7.5, 8.0, 7.9],
        '仰臥起坐(次)': [35, 28, 32, 30, 33],
        '坐姿體前彎(公分)': [15, 18, 20, 14, 19],
        '立定跳遠(公分)': [180, 165, 175, 190, 170]
    })
    
    st.dataframe(example_data)
    
    st.write("""
    **數據要求:**
    - 每個Excel檔案應包含一次測試的完整數據
    - 必須包含'學生ID'或'姓名'欄位用於識別學生
    - 測試項目名稱應保持一致（如'50公尺跑'）
    - 檔案名稱最好包含測試日期 (如 '體適能測試_2023-03-15.xlsx')
    - 上傳多個檔案時將自動進行跨時間比較分析
    
    **Claude API 整合:**
    - 輸入Anthropic API Key以啟用數據分析能力
    - 所有問題與分析將通過Claude AI處理
    - 系統將自動解析問題並生成合適的分析代碼
    """)