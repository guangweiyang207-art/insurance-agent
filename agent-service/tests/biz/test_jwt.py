import jwt
import app.core.config


token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJobS1pbnN1cmFuY2UiLCJzdWIiOiIyIiwidXNlcl9pZCI6MiwidXNlcm5hbWUiOiJodWdlIiwidHlwIjoiYWNjZXNzIiwiaWF0IjoxNzgzOTk1MzMwLCJleHAiOjE3ODM5OTcxMzB9.YDndGxpmlDkkHT-rph5lZKwhH-8LE3iFAERMI8OpajA"

def test_jwt():
#是一段**JWT 解码测试脚本**，用来验证 JWT 能不能用密钥正常解密、打印出 token 里承载的用户信息 payload。
    # 返回的是jwt的第二部分，放的是用户信息
    payload = jwt.decode(
        token, # 要解析的jwt的token
        settings.jwt_secret, # jwt的密钥
        algorithms=['HS256'] # jwt的签名算法
    )

    print(payload)