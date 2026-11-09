-- AI 对话持久化 - Oracle 建表脚本
-- 在 ecology 用户下执行

-- 会话表
CREATE TABLE ai_chat_sessions (
    session_id  VARCHAR2(64) PRIMARY KEY,
    user_id     VARCHAR2(50),
    user_name   VARCHAR2(100),
    title       VARCHAR2(200),
    created_at  TIMESTAMP DEFAULT SYSTIMESTAMP,
    updated_at  TIMESTAMP DEFAULT SYSTIMESTAMP
);

-- 消息表
CREATE TABLE ai_chat_messages (
    id           NUMBER PRIMARY KEY,
    session_id   VARCHAR2(64) NOT NULL,
    seq_num      NUMBER NOT NULL,
    role         VARCHAR2(20),
    content_json CLOB,
    created_at   TIMESTAMP DEFAULT SYSTIMESTAMP,
    CONSTRAINT fk_chat_msg_session FOREIGN KEY (session_id)
        REFERENCES ai_chat_sessions(session_id)
);

-- 自增序列 + 触发器（Oracle 11g 兼容）
CREATE SEQUENCE ai_chat_msg_seq START WITH 1 INCREMENT BY 1 NOCACHE;

CREATE OR REPLACE TRIGGER ai_chat_msg_trg
BEFORE INSERT ON ai_chat_messages
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT ai_chat_msg_seq.NEXTVAL INTO :NEW.id FROM dual;
    END IF;
END;
/

-- 索引
CREATE INDEX idx_chat_msg_session ON ai_chat_messages(session_id, seq_num);
CREATE INDEX idx_chat_session_user ON ai_chat_sessions(user_id);

-- 验证
SELECT 'TABLES CREATED' AS result FROM dual;
