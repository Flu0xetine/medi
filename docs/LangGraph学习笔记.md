# LangGraph 学习笔记

## 1. 图的基本含义

```text
START → greet → add_exclamation → END
```

这表示程序的执行顺序：

- `START`：流程开始。
- `greet`：执行打招呼节点。
- `add_exclamation`：执行添加感叹号节点。
- `END`：流程结束。

在 LangGraph 中，可以把图理解成一条加工流水线：状态依次经过各个节点，每个节点读取当前状态，并返回对状态的更新。

## 2. State 和节点

`State` 是整张图共享的数据。例如：

```python
state = {"text": "小明"}
```

节点本质上是 Python 函数：

```python
def greet(state):
    return {"text": "你好，" + state["text"]}


def add_exclamation(state):
    return {"text": state["text"] + "！"}
```

状态的变化过程：

```text
{"text": "小明"}
        ↓ greet
{"text": "你好，小明"}
        ↓ add_exclamation
{"text": "你好，小明！"}
```

## 3. 返回更新，不直接修改 State

以下两种写法在简单程序中可能得到相同结果。

### 直接修改传入的 State

```python
def greet(state):
    state["text"] = "你好，" + state["text"]
    return state
```

这种写法会修改原来的字典对象，产生副作用。图中出现分支、并行执行或复杂调试时，可能造成混乱。

### 返回需要更新的字段（推荐）

```python
def greet(state):
    return {"text": "你好，" + state["text"]}
```

这里返回的是一份“状态更新”，不一定是完整状态。LangGraph 负责把更新合并到当前状态中。

例如当前状态为：

```python
{
    "text": "小明",
    "count": 3,
    "user_id": 1001,
}
```

节点只返回：

```python
{"text": "你好，小明"}
```

LangGraph 合并后的状态是：

```python
{
    "text": "你好，小明",
    "count": 3,
    "user_id": 1001,
}
```

## 4. 核心结论

> 节点读取当前 `State`，返回需要更新的字段；LangGraph 应用更新后，再把新状态传给下一个节点。

推荐写法：

```python
def node(state):
    return {"字段名": 新值}
```

## 5. Reducer：决定如何合并新旧值

节点决定“返回什么更新”，Reducer 决定“这个更新怎样写进 State”。

### 没有 Reducer：新值覆盖旧值

```python
class State(TypedDict):
    messages: list[str]
```

假设旧值和节点返回值分别是：

```python
旧值 = ["你好"]
新值 = ["最近怎么样？"]
```

因为没有指定 Reducer，所以新值覆盖旧值：

```python
["最近怎么样？"]
```

### 有 Reducer：按照指定规则合并

```python
from typing import Annotated, TypedDict
import operator


class State(TypedDict):
    messages: Annotated[list[str], operator.add]
```

`operator.add` 相当于执行：

```python
旧值 + 新值
```

因此：

```python
["你好"] + ["最近怎么样？"]
```

得到：

```python
["你好", "最近怎么样？"]
```

Reducer 可以理解成：

```text
旧值 + 节点返回的新值
          ↓
      Reducer 处理
          ↓
       State 新值
```

适用原则：

- 姓名、当前状态等只需要保存最新值的字段，通常不需要 Reducer。
- 消息历史、日志、累计结果等需要不断积累的字段，通常需要 Reducer。

也可以编写自己的 Reducer：

```python
def add_numbers(old: int, new: int) -> int:
    return old + new


class State(TypedDict):
    total: Annotated[int, add_numbers]
```

如果旧值为 `2`，节点返回 `3`，最终值就是 `5`。

## 6. Annotated：给类型附加额外说明

`Annotated` 的基本形式是：

```python
Annotated[原始类型, 附加信息]
```

在 LangGraph 中，附加信息经常是 Reducer：

```python
messages: Annotated[list[str], operator.add]
```

拆开理解：

```text
list[str]     → messages 字段是字符串列表
operator.add  → 更新该字段时，使用这个 Reducer 合并新旧值
```

`Annotated` 自己不会执行 `operator.add`。它只是把信息附加在类型上；LangGraph 读取这份信息后，才把 `operator.add` 当作 Reducer 使用。

### Annotated 不是一个有两个值的列表

下面的方括号是类型参数语法：

```python
Annotated[list[str], operator.add]
```

它类似于：

```python
list[str]
dict[str, int]
```

真正的列表数据仍然是：

```python
state = {
    "messages": ["你好", "世界"]
}
```

可以把二者区分为：

```text
Annotated[list[str], operator.add]  → 字段说明书
["你好", "世界"]                    → 字段中的实际数据
```

理论上，可以自己创建普通列表来保存类型和函数：

```python
my_rule = [list[str], operator.add]
```

然后自己规定：第一个位置是类型，第二个位置是 Reducer。但是 Python 类型系统和 LangGraph 不认识这项私人约定；还需要自己编写解析逻辑。

`Annotated` 的优势在于它是标准结构：

```text
Annotated[基础类型, 元数据...]
```

编辑器、类型工具和 LangGraph 可以按照这个统一约定读取它。

### 查看 Annotated 的附加信息

可以使用 `get_origin()` 和 `get_args()`：

```python
from typing import Annotated, get_args, get_origin
import operator


annotation = Annotated[list[str], operator.add]

print(get_origin(annotation))
print(get_args(annotation))
```

输出大致为：

```python
<class 'typing.Annotated'>
(list[str], <built-in function add>)
```

分别取出原始类型和 Reducer：

```python
field_type, reducer = get_args(annotation)

print(field_type)  # list[str]
print(reducer)     # operator.add

result = reducer(["你好"], ["世界"])
print(result)      # ["你好", "世界"]
```

从 `TypedDict` 中读取时，可以使用：

```python
from typing import get_type_hints


hints = get_type_hints(State, include_extras=True)
annotation = hints["messages"]
field_type, reducer = get_args(annotation)
```

这里要写 `include_extras=True`，否则附加信息可能被移除，只剩下原始类型。

## 7. Reducer 与 Annotated 的关系

下面这行代码可以按三层理解：

```python
messages: Annotated[list[str], operator.add]
```

1. `messages`：State 的字段名。
2. `list[str]`：字段的数据类型。
3. `operator.add`：该字段的 Reducer。

一句话总结：

> `Annotated` 负责把 Reducer 标记在字段类型上，Reducer 负责合并该字段的新旧值。
