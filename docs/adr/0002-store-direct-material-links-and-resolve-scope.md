# Store direct material links and resolve effective scope

V8 只持久化用户确认的资料直接归属，不把目标到课程、课程到知识点的继承结果重复写入数据库；有效资料范围由统一模块按当前学习层级即时解析。这样避免层级调整后出现成批过期关系，并让 scoped RAG、活动生成和页面查询共享同一套确定性语义；批量写入采用原子全成或全不成，LLM 不拥有正式归属写权限。
