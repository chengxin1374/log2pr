"""
电商系统测试模块。

E-commerce system test module.

这个模块包含故意制造的跨文件 bug，用于测试 log2pr 的自动修复能力。

错误案例：
1. KeyError: 无效折扣码导致 validators.py 中字典访问失败
2. TypeError: None 折扣率导致 calculations.py 中乘法失败

文件结构：
- main.py: 入口文件，运行测试用例
- models.py: 数据模型定义
- services/order_service.py: 订单服务，协调各模块
- services/payment_service.py: 支付服务
- utils/validators.py: 验证工具，包含 KeyError bug
- utils/calculations.py: 计算工具，包含 TypeError bug
"""
