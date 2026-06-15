import os
from pathlib import Path

def create_test_contracts():
    """創建測試用合約文件"""
    # 確保 corpus 目錄存在
    corpus_dir = Path("corpus")
    corpus_dir.mkdir(exist_ok=True)
    
    # 測試合約內容
    contract_content = """合約書

立約人：王大明（身份證字號：A123456789）
聯絡電話：0912-345-678
電子郵件：example@example.com
地址：台北市信義區信義路五段7號
統編：12345678

合約內容：
1. 甲方（以下簡稱「公司」）與乙方（以下簡稱「客戶」）同意以下條款...
2. 合約金額：新台幣1,000,000元整
3. 合約期間：自2023年1月1日起至2023年12月31日止
4. 付款方式：銀行轉帳（銀行代碼：012，帳號：123456789012）
5. 聯絡人：陳經理 0988-777-666

注意事項：
- 本合約內容為機密文件，未經許可不得外洩。
- 合約編號：CT2023-00123
"""
    
    # 創建多個測試文件
    for i in range(1, 6):
        file_path = corpus_dir / f"test_contract_{i}.txt"
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(contract_content.replace("CT2023-00123", f"CT2023-{i:05d}"))
    
    print(f"已創建 5 個測試合約文件在 {corpus_dir.absolute()}")

if __name__ == "__main__":
    create_test_contracts()
