import boto3
import pandas as pd
from datetime import datetime, date
from typing import Tuple
from botocore.exceptions import ClientError
import streamlit as st


# boto 條件 + ASUS 表格呈現邏輯
def query_finding(region: str) -> pd.DataFrame:
    # 用於轉換 "AWS_region",  "ASUS_業務_region"
    region_mapping = {
        "ap-northeast-1": "Tokyo",  # for test: Going Cloud's region
        "us-west-2": "Oregon",  # ASUS: account_211
        "ap-southeast-1": "APAC",  # ASUS: account_378
        "eu-central-1": "EMEA",  # ASUS: account_378
        "sa-east-1": "SSA",  # ASUS: account_378
    }

    # 依指定 region 建立 boto client
    client = boto3.client("securityhub", region_name=region)

    # 篩選 findings 的 filters
    filters = {
        "WorkflowStatus": [
            {"Value": "NEW", "Comparison": "EQUALS"},
            {"Value": "NOTIFIED", "Comparison": "EQUALS"},
        ],
        "SeverityLabel": [{"Value": "INFORMATIONAL", "Comparison": "NOT_EQUALS"}],
    }

    finding_list = []
    next_token = None
    today_date = date.today()  # 確保每筆資料日期一致

    try:
        while True:
            if next_token:
                response = client.get_findings(Filters=filters, NextToken=next_token)
            else:
                response = client.get_findings(Filters=filters)

            for finding in response.get("Findings", []):
                # 取 Remediation URL，若無則給預設字串
                remediation = (
                    finding.get("Remediation", {})
                    .get("Recommendation", {})
                    .get("Url", "No URL provided.")
                )

                # 取得 Resource ARN 並解析
                resource_arn = (
                    finding.get("Resources")[0].get("Id")
                    if finding.get("Resources")
                    and finding.get("Resources")[0].get("Id")
                    else "resource_not_found"
                )
                count_arn = resource_arn.split(":")
                recommendation_result = "unknown"
                if len(count_arn) == 7:
                    resource_type = count_arn[5]
                    resource_name = count_arn[6]
                    recommendation_result = f"{resource_type}/{resource_name}"
                elif len(count_arn) == 6:
                    recommendation_result = count_arn[5]

                # 組成 DataFrame 用 dict
                data = {
                    "Workflow status": finding.get("Workflow", {}).get("Status", ""),
                    "Region": region_mapping.get(
                        region, f"{region} 尚未加入 region_mapping"
                    ),
                    "Status": "",  # 保留欄位 for 格式完整性
                    "PIC": "",  # 保留欄位 for 格式完整性
                    "Due": "",  # 保留欄位 for 格式完整性
                    "ID": finding.get("Compliance", {}).get("SecurityControlId", ""),
                    "Title": finding.get("Title", ""),
                    "Severity": finding.get("Severity", {}).get("Label", ""),
                    "Failed check": "",  # 保留欄位 for 格式完整性
                    "Passed check": "",  # 保留欄位 for 格式完整性
                    "Custom parameters": "",  # 保留欄位 for 格式完整性
                    "Remediation": remediation,
                    "Recommendation": recommendation_result,
                    "Action": "",  # 報告時由 ASUS 填寫，保留欄位 for 格式完整性
                    "Remark": "",  # 報告時由 ASUS 填寫，保留欄位 for 格式完整性
                    "Created_Date": today_date,
                }
                finding_list.append(data)

            next_token = response.get("NextToken")
            if not next_token:
                break

    except ClientError as e:
        if e.response["Error"]["Code"] == "InvalidAccessException":
            raise ValueError(f"{region} not enable Security Hub.")
        else:
            raise e

    df = pd.DataFrame(finding_list)
    return df


@st.cache_data
def combine_findings_for_regions(region_list: list) -> Tuple[pd.DataFrame, list]:
    multi_region_df = []
    invalid_region_list = []

    for region in region_list:
        try:
            df = query_finding(region)
            multi_region_df.append(df)
        except ValueError:
            invalid_region_list.append(region)

    combined_df = (
        pd.concat(multi_region_df, ignore_index=True)
        if multi_region_df
        else pd.DataFrame()
    )
    return combined_df, invalid_region_list


def sort_findings(df: pd.DataFrame) -> pd.DataFrame:
    # severity mapping & 防呆（空值先轉成空字串）
    df["Severity"] = df["Severity"].fillna("")
    severity_mapping = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
    df["SeverityScore"] = df["Severity"].map(severity_mapping).fillna(0)

    df = df.sort_values(
        by=["SeverityScore", "ID", "Region"], ascending=[False, True, True]
    )
    df = df.drop(columns=["SeverityScore"])

    # 移除重複的 remediation 和 recommendation
    df = df.drop_duplicates(subset=["Remediation", "Recommendation"], keep="first")

    # 最後依照 ID 和 Region 排序
    df = df.sort_values(by=["ID", "Region"], ascending=True)
    return df


def streamlit_logic(region_list: list):
    st.set_page_config(layout="wide")
    combined_df, invalid_region_list = combine_findings_for_regions(region_list)
    df = sort_findings(combined_df)

    st.sidebar.write("Query findings")
    severity_options = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    selected_severity = st.sidebar.multiselect(
        "By Severity", severity_options, default=severity_options
    )
    if selected_severity:
        df = df[df["Severity"].isin(selected_severity)]

    workflow_options = ["NEW", "NOTIFIED"]
    selected_workflow = st.sidebar.multiselect(
        "By Workflow status", workflow_options, default=workflow_options
    )
    if selected_workflow:
        df = df[df["Workflow status"].isin(selected_workflow)]

    st.write("### AWS Security Hub 整理表")
    st.dataframe(df, hide_index=True)

    if invalid_region_list:
        st.write("### AWS Region without security hub")
        st.error(
            f"Regions not subscribed to AWS Security Hub: {', '.join(invalid_region_list)}"
        )


def main(region_list: list):
    streamlit_logic(region_list)


if __name__ == "__main__":
    region_list = [
        "ap-southeast-1",  # ASUS 378
        "eu-central-1",  # ASUS 378
        "sa-east-1",  # ASUS 378
        "us-west-2",  # ASUS 211
    ]
    main(region_list)
