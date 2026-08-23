# AI Study Assistant 📚

基于 RAG（Retrieval-Augmented Generation，检索增强生成）的智能学习助手。

本项目面向学生学习场景，利用大语言模型与知识库检索技术，实现课程资料上传、知识库构建以及基于个人学习资料的智能问答。

用户可以上传 PDF、DOCX 等课程资料，系统会自动完成文本解析、文本切分、向量化存储，并结合大语言模型回答与学习内容相关的问题。

---

## ✨ Features

### 📄 学习资料管理

- 支持上传 PDF、DOCX、TXT 等格式文件
- 自动提取文档内容
- 对长文档进行文本切分（Chunking）
- 保存文档摘要信息


### 🔍 RAG 知识库问答

- 基于 Embedding 模型生成文本向量
- 使用 ChromaDB 构建本地向量数据库
- 支持语义检索与关键词检索结合的 Hybrid Search
- 根据检索到的课程资料生成相关回答


### 🤖 大语言模型交互

- 支持本地 Ollama 大语言模型调用
- 支持流式输出回答
- 支持多轮对话上下文记忆


### 📚 学习辅助场景（持续开发）

计划增加：

- 自动总结章节重点
- 生成考试复习提纲
- 根据资料生成练习题
- 错题分析与知识薄弱点总结

---

## 工作流程

整体工作流程：

用户上传课程资料

↓

文档解析
(PDF/DOCX/TXT)

↓

文本切分
(Text Chunking)

↓

Embedding向量生成

↓

ChromaDB存储

↓

用户输入问题

↓

Hybrid Search检索相关知识

↓

LLM生成回答

---

## 核心组成部分

### Ollama

提供本地大语言模型能力，包括：

- Embedding 模型
- Chat 模型


### ChromaDB

用于存储和查询文本向量，实现知识库检索。


### Streamlit

用于构建用户交互界面，实现：

- 文件上传
- 参数配置
- 对话展示

---

# 🛠️ 技术栈

## Programming Language

- Python


## AI / LLM

- RAG
- Embedding
- Ollama


## Framework

- Streamlit


## Vector Database

- ChromaDB


## Document Processing

- PyPDF2
- python-docx
- openpyxl


---

# 📚 Future Plans

后续计划：

- [ ] 学习总结模式
- [ ] 自动生成考试重点
- [ ] 自动生成练习题
- [ ] 错题知识点分析
- [ ] 学习进度管理