import boto3
import pandas as pd
import streamlit as st


### For CloudWatch alarm's info
def format_condition(alarm):
    metric = alarm.get("MetricName")
    op = alarm.get("ComparisonOperator")
    if op == "GreaterThanThreshold":
        op = ">"
    elif op == "LessThanThreshold":
        op = "<"
    elif op == "GreaterThanOrEqualToThreshold":
        op = ">="
    elif op == "LessThanOrEqualToThreshold":
        op = "<="
    elif op == "EqualToThreshold":
        op = "=="
    elif op == "NotEqualToThreshold":
        op = "!="
    else:
        op = "Unknown Operator"
    threshold = alarm.get("Threshold")
    periods = alarm.get("EvaluationPeriods", 0)
    period = alarm.get("Period", 0) // 60
    minutes = period * periods

    return (
        f"{metric} {op} {threshold} for {periods} datapoints within {minutes} minutes"
    )


def get_MetricAlarms(region: str):
    client = boto3.client("cloudwatch", region_name=region)
    paginator = client.get_paginator("describe_alarms")
    alarms_data = []

    for page in paginator.paginate():
        for alarm in page.get("MetricAlarms", []):
            # 欄位邏輯處理
            alarm_name = alarm.get("AlarmName")
            condition = format_condition(alarm)
            actions = alarm.get("AlarmActions", [])
            last_updated = alarm.get("StateUpdatedTimestamp")
            dimensions = alarm.get("Dimensions", [])
            dimensions = (
                ", ".join([f"{d['Name']}={d['Value']}" for d in dimensions])
                if dimensions
                else ""
            )

            # 欄位 append 共 6 欄
            alarms_data.append(
                {
                    "Region": region,
                    "AlarmName": alarm_name,
                    "Resource": dimensions,
                    "Condition": condition,
                    "Actions": ", ".join(actions) if actions else "None",
                    "Last_updated_date": last_updated.strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
    # DataFrame 共 6 欄
    df = pd.DataFrame(
        alarms_data,
        columns=[
            "Region",
            "AlarmName",
            "Resource",
            "Condition",
            "Actions",
            "Last_updated_date",
        ],
    )
    return df


def get_CompositeAlarms(region: str):
    client = boto3.client("cloudwatch", region_name=region)
    paginator = client.get_paginator("describe_alarms")
    alarms_data = []

    for page in paginator.paginate(AlarmTypes=["CompositeAlarm"]):
        for alarm in page.get("CompositeAlarms", []):
            # 欄位邏輯處理
            alarm_name = alarm.get("AlarmName", None)
            alarm_rule = alarm.get("AlarmRule", None)
            actions = alarm.get("AlarmActions", None)
            last_updated = alarm.get("StateUpdatedTimestamp", None)

            # 欄位 append 共 6 欄
            alarms_data.append(
                {
                    "Region": region,
                    "AlarmName": alarm_name,
                    "Resource": "",
                    "Condition": alarm_rule,
                    "Actions": ", ".join(actions) if actions else "None",
                    "Last_updated_date": last_updated.strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
    # DataFrame 共 6 欄
    df = pd.DataFrame(
        alarms_data,
        columns=[
            "Region",
            "AlarmName",
            "Resource",
            "Condition",
            "Actions",
            "Last_updated_date",
        ],
    )
    return df


def get_multi_alarms_in_multi_regions(regions: list) -> pd.DataFrame:
    all_alarms_data = []

    for region in regions:
        metric_alarms_df = get_MetricAlarms(region)
        parent_alarms_df = get_CompositeAlarms(region)

        # 合併 Metric Alarms 和 Composite Alarms
        all_alarms_data.append(metric_alarms_df)
        all_alarms_data.append(parent_alarms_df)

    # 合併所有的 DataFrame
    combined_df = pd.concat(all_alarms_data, ignore_index=True)

    return combined_df


###For SNS topic's info
def get_multi_sns_in_multi_regions(regions: list) -> pd.DataFrame:
    sns_data = []

    for region in regions:
        sns_client = boto3.client("sns", region_name=region)

        try:
            topics_response = sns_client.list_topics()
            topic_arns = [t["TopicArn"] for t in topics_response.get("Topics", [])]

            for topic_arn in topic_arns:
                # Get subscriptions for each topic
                paginator = sns_client.get_paginator("list_subscriptions_by_topic")
                subscriptions_found = False  # Flag to check if there are subscriptions

                for page in paginator.paginate(TopicArn=topic_arn):
                    if page["Subscriptions"]:
                        for sub in page["Subscriptions"]:
                            sns_data.append(
                                {
                                    "Region": region,
                                    "TopicArn": topic_arn,
                                    "Protocol": sub["Protocol"],
                                    "Endpoint": sub["Endpoint"],
                                }
                            )
                        subscriptions_found = True

                # If no subscriptions, add topic with None for Endpoint
                if not subscriptions_found:
                    sns_data.append(
                        {
                            "Region": region,
                            "TopicArn": topic_arn,
                            "Protocol": "None",
                            "Endpoint": "None",
                        }
                    )

        except Exception as e:
            sns_data.append(
                {
                    "Region": region,
                    "TopicArn": "ERROR",
                    "Protocol": "ERROR",
                    "Endpoint": str(e),
                }
            )

    df = pd.DataFrame(sns_data)

    # Group by Region, TopicArn, and Protocol, then join endpoints if necessary
    grouped_df = (
        df.groupby(["Region", "TopicArn", "Protocol"])["Endpoint"]
        .apply(lambda x: ", ".join(sorted(x)) if x.iloc[0] != "None" else "None")
        .reset_index()
    )

    return grouped_df


### Streamlit login
def main(regions: list):
    alarms_df = get_multi_alarms_in_multi_regions(REGIONS)
    sns_df = get_multi_sns_in_multi_regions(REGIONS)

    st.subheader("Cloud Watch alarm")
    st.dataframe(alarms_df)

    st.subheader("SNS topic")
    st.dataframe(sns_df)


if __name__ == "__main__":
    REGIONS = ["ap-southeast-1", "eu-central-1", "sa-east-1"]
    main(REGIONS)
