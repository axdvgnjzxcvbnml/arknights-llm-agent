"""爬虫解析器单元测试（审计报告 M6 遗留）。

为 5 个解析器写单元测试，全部使用**自造 HTML fixture**（不复制 PRTS Wiki 真实素材，
避免版权风险）。覆盖正常解析、边界条件、异常输入。

测试的模块：
- knowledge/crawler/_html_utils.py（章节定位/表格配对/JS对象提取）
- knowledge/crawler/parse_operators.py（干员解析：meta/技能/特性/0基星级）
- knowledge/crawler/parse_enemies.py（敌人解析：多级别/boss布局/名称跨行）
- knowledge/crawler/parse_stages.py（关卡解析：信息卡/敌情表）
- knowledge/crawler/parse_guides.py（攻略文本生成：从JSON→检索文本块）
"""

import pytest

from knowledge.crawler._html_utils import (
    extract_js_object,
    get_section,
    parse_html,
    table_rows,
    th_td_pairs,
)
from knowledge.crawler.parse_enemies import _clean_enemy_data, parse_enemy
from knowledge.crawler.parse_guides import (
    build_guides,
    enemy_to_guide,
    operator_to_guide,
    stage_to_guide,
)
from knowledge.crawler.parse_operators import (
    _parse_meta,
    _parse_skills,
    _parse_trait,
    parse_operator,
)
from knowledge.crawler.parse_stages import parse_stage


# ===========================================================================
# _html_utils.py
# ===========================================================================

class TestExtractJsObject:
    def test_normal_object(self):
        text = 'var char_info = {"name": "阿米娅", "star": 4};'
        obj = extract_js_object(text, "char_info")
        assert obj["name"] == "阿米娅"
        assert obj["star"] == 4

    def test_trailing_commas_removed(self):
        # JS 允许尾随逗号 ,} / ,]，JSON 不允许；_strip_trailing_commas 应清洗
        text = 'var data = {"a": 1, "b": [2, 3,], };'
        obj = extract_js_object(text, "data")
        assert obj == {"a": 1, "b": [2, 3]}

    def test_multiline_trailing_comma(self):
        text = '''var char_info = {
            "name": "测试",
            "star": 2,
        };'''
        obj = extract_js_object(text, "char_info")
        assert obj["name"] == "测试"
        assert obj["star"] == 2

    def test_var_not_found_returns_empty(self):
        text = 'var other = {"x": 1};'
        assert extract_js_object(text, "char_info") == {}

    def test_nested_braces(self):
        text = 'var info = {"a": {"b": {"c": 1}}, "d": [1, 2]};'
        obj = extract_js_object(text, "info")
        assert obj["a"]["b"]["c"] == 1
        assert obj["d"] == [1, 2]

    def test_equals_no_spaces(self):
        # PRTS 实际格式 var char_info={...}（等号两侧无空格）
        text = 'var char_info={"name":"x"};'
        obj = extract_js_object(text, "char_info")
        assert obj["name"] == "x"


class TestGetSection:
    def _make_html(self):
        return """
        <html><body>
        <div class="mw-heading mw-heading2"><h2 id="特性">特性</h2></div>
        <p>特性描述文本</p>
        <table class="wikitable"><tr><td>数据</td></tr></table>
        <div class="mw-heading mw-heading2"><h2 id="获得方式">获得方式</h2></div>
        <p>获得方式文本</p>
        </body></html>
        """

    def test_section_found(self):
        soup = parse_html(self._make_html())
        nodes = get_section(soup, "特性")
        assert len(nodes) == 2  # <p> + <table>
        assert nodes[0].name == "p"
        assert nodes[1].name == "table"

    def test_section_not_found_returns_empty(self):
        soup = parse_html(self._make_html())
        assert get_section(soup, "不存在的章节") == []

    def test_section_stops_at_next_heading(self):
        soup = parse_html(self._make_html())
        nodes = get_section(soup, "特性")
        # 不应包含"获得方式"章节的内容
        texts = [n.get_text(strip=True) for n in nodes if n.name == "p"]
        assert "获得方式文本" not in texts


class TestThTdPairs:
    def test_simple_pairs(self):
        html = """<table>
        <tr><th>名称</th><td>源石虫</td></tr>
        <tr><th>地位</th><td>普通</td></tr>
        <tr><th>攻击力</th><td>100</td></tr>
        </table>"""
        soup = parse_html(html)
        pairs = th_td_pairs(soup.table)
        assert pairs["名称"] == "源石虫"
        assert pairs["地位"] == "普通"
        assert pairs["攻击力"] == "100"

    def test_boss_layout_name_pending(self):
        # boss 特殊布局：名称/地位的 th 在一行，值在下一行 td
        html = """<table>
        <tr><th>名称</th><th>地位</th></tr>
        <tr><td>碎骨</td><td>领袖</td></tr>
        <tr><th>攻击力</th><td>500</td></tr>
        </table>"""
        soup = parse_html(html)
        pairs = th_td_pairs(soup.table)
        assert pairs["名称"] == "碎骨"
        assert pairs["地位"] == "领袖"
        assert pairs["攻击力"] == "500"

    def test_th_only_row_pending(self):
        # 全 th 行挂起，下一行全 td 配对
        html = """<table>
        <tr><th>字段A</th><th>字段B</th></tr>
        <tr><td>值A</td><td>值B</td></tr>
        </table>"""
        soup = parse_html(html)
        pairs = th_td_pairs(soup.table)
        assert pairs["字段A"] == "值A"
        assert pairs["字段B"] == "值B"


class TestTableRows:
    def test_normal_rows(self):
        html = """<table>
        <tr><th>头1</th><th>头2</th></tr>
        <tr><td>a</td><td>b</td></tr>
        </table>"""
        soup = parse_html(html)
        rows = table_rows(soup.table)
        assert rows == [["头1", "头2"], ["a", "b"]]

    def test_empty_rows_skipped(self):
        html = """<table>
        <tr><th>头</th></tr>
        <tr><td></td><td></td></tr>
        <tr><td>数据</td></tr>
        </table>"""
        soup = parse_html(html)
        rows = table_rows(soup.table)
        assert len(rows) == 2  # 空行被跳过
        assert rows[1] == ["数据"]


# ===========================================================================
# parse_operators.py
# ===========================================================================

def _operator_html(name="测试干员", star=4, with_skills=True, with_trait=True):
    """自造干员页 HTML fixture（不复制 PRTS 素材）。"""
    skill_section = ""
    if with_skills:
        skill_section = """
        <div class="mw-heading mw-heading2"><h2 id="技能">技能</h2></div>
        <table class="wikitable nomobile">
        <tr><td></td><th>冲锋号令·β型</th><th>自动回复</th><th>手动触发</th></tr>
        <tr><th>等级</th><th>描述</th><th>初始</th><th>消耗</th><th>持续</th></tr>
        <tr><td>1</td><td>立即获得1点部署费用</td><td>0</td><td>40</td><td>0</td></tr>
        <tr><td>7</td><td>立即获得2点部署费用</td><td>10</td><td>35</td><td>0</td></tr>
        </table>
        """
    trait_section = ""
    if with_trait:
        trait_section = """
        <div class="mw-heading mw-heading2"><h2 id="特性">特性</h2></div>
        <table class="wikitable">
        <tr><th>分支</th><th>描述</th></tr>
        <tr><td>先锋</td><td>击杀敌人后获得1点部署费用</td></tr>
        <tr><td>分支信息</td></tr>
        <tr><td>先锋的分支说明文本</td></tr>
        </table>
        """
    return """
    <html><head><title>%s - PRTS</title></head><body>
    <script>var char_info = {"name": "%s", "nameEn": "Test", "star": %d, "class": "先锋", "branch": "冲锋手", "pos": "近战", "tag": "费用回复"};</script>
    %s
    %s
    <div class="mw-heading mw-heading2"><h2 id="获得方式">获得方式</h2></div>
    <table class="wikitable"><tr><th>获取途径</th><td>公开招募</td></tr></table>
    </body></html>
    """ % (name, name, star, trait_section, skill_section)


class TestParseOperatorMeta:
    def test_star_zero_based_encoding(self):
        # PRTS star 是 0 基编码：star=4 → 游戏内 5 星
        soup = parse_html(_operator_html(star=4))
        meta = _parse_meta(soup)
        assert meta["star"] == 4
        assert meta["star_rating"] == 5
        assert meta["name"] == "测试干员"
        assert meta["class"] == "先锋"

    def test_six_star_operator(self):
        soup = parse_html(_operator_html(star=5))
        meta = _parse_meta(soup)
        assert meta["star_rating"] == 6  # 能天使 6 星

    def test_three_star_operator(self):
        soup = parse_html(_operator_html(star=2))
        meta = _parse_meta(soup)
        assert meta["star_rating"] == 3  # 芬 3 星


class TestParseOperatorSkills:
    def test_skill_parsed(self):
        soup = parse_html(_operator_html(with_skills=True))
        skills = _parse_skills(soup)
        assert len(skills) == 1
        assert skills[0]["name"] == "冲锋号令·β型"
        assert skills[0]["type"] == "自动回复"
        assert len(skills[0]["levels"]) == 2
        assert skills[0]["levels"][0]["level"] == "1"
        assert skills[0]["levels"][0]["desc"] == "立即获得1点部署费用"
        assert skills[0]["levels"][0]["cost"] == "40"

    def test_no_skill_section(self):
        soup = parse_html(_operator_html(with_skills=False))
        assert _parse_skills(soup) == []


class TestParseOperatorTrait:
    def test_trait_branch_desc(self):
        soup = parse_html(_operator_html(with_trait=True))
        trait = _parse_trait(soup)
        assert trait["分支"] == "先锋"
        assert "击杀敌人后获得1点部署费用" in trait["描述"]
        assert trait["分支信息"] == "先锋的分支说明文本"

    def test_no_trait_section(self):
        soup = parse_html(_operator_html(with_trait=False))
        assert _parse_trait(soup) == {}


class TestParseOperatorFull:
    def test_full_parse(self):
        html = _operator_html(name="阿米娅", star=4)
        op = parse_operator(html)
        assert op["name"] == "阿米娅"
        assert op["meta"]["star_rating"] == 5
        assert len(op["skills"]) == 1
        assert op["trait"]["分支"] == "先锋"
        assert op["obtain"]["获取途径"] == "公开招募"


# ===========================================================================
# parse_enemies.py
# ===========================================================================

def _enemy_html(name="源石虫", levels=(0, 1), boss_layout=False):
    """自造敌人页 HTML fixture。"""
    sections = ""
    for lv in levels:
        if boss_layout:
            # boss 布局：名称/地位 th 单独一行，值在下一行
            level_table = """
            <table class="enemy-info-level wikitable">
            <tr><th>名称</th><th>地位</th></tr>
            <tr><td>%s</td><td>领袖</td></tr>
            <tr><th>种类</th><td>BOSS</td></tr>
            <tr><th>最大生命值</th><td>10000</td></tr>
            <tr><th>攻击力</th><td>500</td></tr>
            <tr><td><i>第一特性</i><i>第二特性</i></td></tr>
            </table>
            """ % name
        else:
            level_table = """
            <table class="enemy-info-level wikitable">
            <tr><th>名称</th><td>%s</td></tr>
            <tr><th>地位</th><td>普通</td></tr>
            <tr><th>种类</th><td>感染生物</td></tr>
            <tr><th>最大生命值</th><td>200</td></tr>
            <tr><th>攻击力</th><td>50</td></tr>
            <tr><th>防御力</th><td>10</td></tr>
            <tr><td><i>低机动</i></td></tr>
            </table>
            """ % name
        sections += """
        <div class="mw-heading mw-heading2"><h2 id="级别%d">级别%d</h2></div>
        %s
        """ % (lv, lv, level_table)
    return """
    <html><body>%s</body></html>
    """ % sections


class TestParseEnemy:
    def test_single_level(self):
        enemy = parse_enemy(_enemy_html(levels=(0,)))
        assert enemy["name"] == "源石虫"
        assert len(enemy["levels"]) == 1
        assert enemy["levels"][0]["level"] == 0
        data = enemy["levels"][0]["data"]
        assert data["名称"] == "源石虫"
        assert data["地位"] == "普通"
        assert data["最大生命值"] == "200"
        assert data["攻击力"] == "50"

    def test_multiple_levels(self):
        enemy = parse_enemy(_enemy_html(levels=(0, 1, 2)))
        assert len(enemy["levels"]) == 3
        assert [l["level"] for l in enemy["levels"]] == [0, 1, 2]

    def test_boss_layout_name_cross_row(self):
        # boss 布局：名称/地位的 th 与 td 不在同一行
        enemy = parse_enemy(_enemy_html(name="碎骨", levels=(0,), boss_layout=True))
        assert enemy["name"] == "碎骨"
        data = enemy["levels"][0]["data"]
        assert data["名称"] == "碎骨"
        assert data["地位"] == "领袖"
        assert data["种类"] == "BOSS"
        assert data["最大生命值"] == "10000"

    def test_traits_extracted(self):
        enemy = parse_enemy(_enemy_html(levels=(0,)))
        traits = enemy["levels"][0]["data"]["特性"]
        assert isinstance(traits, list)
        assert "低机动" in traits

    def test_boss_traits_multiple(self):
        enemy = parse_enemy(_enemy_html(name="碎骨", levels=(0,), boss_layout=True))
        traits = enemy["levels"][0]["data"]["特性"]
        assert "第一特性" in traits
        assert "第二特性" in traits


class TestCleanEnemyData:
    def test_annotated_field_names_normalized(self):
        # PRTS 表头常带注释（如"地位 战斗中所使用的数据"），按前缀归并
        data = {
            "地位 战斗中所使用的数据": "普通",
            "最大生命值": "200",
            "名称": "源石虫",
        }
        cleaned = _clean_enemy_data(data)
        assert cleaned["地位"] == "普通"
        assert "地位 战斗中所使用的数据" not in cleaned
        assert cleaned["最大生命值"] == "200"


# ===========================================================================
# parse_stages.py
# ===========================================================================

def _stage_html(code="3-8", name="3-8 黄昏", with_enemies=True):
    """自造关卡页 HTML fixture。"""
    enemy_section = ""
    if with_enemies:
        enemy_section = """
        <div class="mw-heading mw-heading2"><h2 id="敌方情报">敌方情报</h2></div>
        <table class="stage-enemy-table wikitable">
        <tr><td colspan="5">敌方情报</td></tr>
        <tr><th>头像</th><th>名称</th><th>数量</th><th>地位</th><th>级别</th></tr>
        <tr><td></td><td>碎骨</td><td>1</td><td>领袖</td><td>0</td></tr>
        <tr><td></td><td>士兵</td><td>5</td><td>普通</td><td>0</td></tr>
        </table>
        """
    return f"""
    <html><head><title>{code} - PRTS - 玩家共同编写的明日方舟百科</title></head><body>
    <div class="mw-heading mw-heading2"><h2 id="普通">普通</h2></div>
    <table class="wikitable">
    <tr><th>{name}</th></tr>
    <tr><td>关卡描述文本</td></tr>
    <tr><th>解锁条件</th><td>通关3-7</td></tr>
    <tr><th>推荐等级</th><td>精英1 lv.40</td></tr>
    <tr><th>作战消耗</th><td>12理智</td></tr>
    </table>
    <div class="mw-heading mw-heading2"><h2 id="突袭">突袭</h2></div>
    <table class="wikitable">
    <tr><th>{name}（突袭）</th></tr>
    <tr><td>突袭关卡描述</td></tr>
    <tr><th>突袭附加条件</th><td>敌人攻击力+20%</td></tr>
    </table>
    {enemy_section}
    </body></html>
    """


class TestParseStage:
    def test_normal_mode_info(self):
        stage = parse_stage(_stage_html())
        assert stage["code"] == "3-8"
        assert stage["normal"]["name"] == "3-8 黄昏"
        assert stage["normal"]["desc"] == "关卡描述文本"
        assert stage["normal"]["解锁条件"] == "通关3-7"
        assert stage["normal"]["推荐等级"] == "精英1 lv.40"
        assert stage["normal"]["作战消耗"] == "12理智"

    def test_raid_mode(self):
        stage = parse_stage(_stage_html())
        assert stage["raid"]["name"] == "3-8 黄昏（突袭）"
        assert stage["raid"]["突袭附加条件"] == "敌人攻击力+20%"

    def test_enemy_list(self):
        stage = parse_stage(_stage_html())
        assert len(stage["enemies"]) == 2
        assert stage["enemies"][0]["名称"] == "碎骨"
        assert stage["enemies"][0]["数量"] == "1"
        assert stage["enemies"][0]["地位"] == "领袖"
        assert stage["enemies"][1]["名称"] == "士兵"
        assert stage["enemies"][1]["数量"] == "5"

    def test_no_enemy_section(self):
        stage = parse_stage(_stage_html(with_enemies=False))
        assert stage["enemies"] == []

    def test_code_from_title(self):
        stage = parse_stage(_stage_html(code="1-7", name="1-7 万岁"))
        assert stage["code"] == "1-7"


# ===========================================================================
# parse_guides.py
# ===========================================================================

class TestOperatorToGuide:
    def test_basic_operator(self):
        op = {
            "name": "能天使",
            "meta": {"class": "狙击", "branch": "速射手", "pos": "远程", "tag": "输出"},
            "trait": {"描述": "优先攻击空中单位"},
            "skills": [{"name": "扫射模式", "type": "自动回复",
                        "levels": [{"desc": "攻击力+10%", "level": "1"}]}],
        }
        guide = operator_to_guide(op)
        assert guide["title"] == "干员攻略_能天使"
        assert "能天使" in guide["text"]
        assert "速射手" in guide["text"]
        assert "优先攻击空中单位" in guide["text"]
        assert "扫射模式" in guide["text"]

    def test_operator_no_skills(self):
        op = {"name": "测试", "meta": {"class": "先锋"}, "trait": {}, "skills": []}
        guide = operator_to_guide(op)
        assert guide["title"] == "干员攻略_测试"
        assert "技能" not in guide["text"]  # 无技能时不写技能段


class TestEnemyToGuide:
    def test_basic_enemy(self):
        enemy = {
            "name": "源石虫",
            "levels": [{"level": 0, "data": {
                "地位": "普通", "种类": "感染生物",
                "最大生命值": "200", "攻击力": "50", "防御力": "10",
            }}],
        }
        guide = enemy_to_guide(enemy)
        assert guide["title"] == "敌人攻略_源石虫"
        assert "源石虫" in guide["text"]
        assert "级别0" in guide["text"]
        assert "最大生命值200" in guide["text"]
        assert "攻击力50" in guide["text"]

    def test_enemy_multiple_levels(self):
        enemy = {
            "name": "碎骨",
            "levels": [
                {"level": 0, "data": {"地位": "领袖", "攻击力": "500"}},
                {"level": 1, "data": {"地位": "精英", "攻击力": "800"}},
            ],
        }
        guide = enemy_to_guide(enemy)
        assert "级别0" in guide["text"]
        assert "级别1" in guide["text"]
        assert "攻击力500" in guide["text"]
        assert "攻击力800" in guide["text"]


class TestStageToGuide:
    def test_basic_stage(self):
        stage = {
            "code": "3-8",
            "normal": {"name": "3-8 黄昏", "desc": "描述", "推荐等级": "精英1",
                       "作战消耗": "12理智"},
            "enemies": [{"名称": "碎骨", "数量": "1", "级别": "0", "地位": "领袖"}],
        }
        guide = stage_to_guide(stage)
        assert guide["title"] == "关卡攻略_3-8_3-8 黄昏"
        assert "3-8" in guide["text"]
        assert "推荐等级：精英1" in guide["text"]
        assert "碎骨×1" in guide["text"]
        assert "0级领袖" in guide["text"]

    def test_stage_no_enemies(self):
        stage = {"code": "1-1", "normal": {"name": "1-1 黑暗时代·上"}, "enemies": []}
        guide = stage_to_guide(stage)
        assert "敌人配置" not in guide["text"]


class TestBuildGuides:
    def test_batch_build(self):
        ops = [{"name": "A", "meta": {}, "trait": {}, "skills": []}]
        enemies = [{"name": "B", "levels": []}]
        stages = [{"code": "1-1", "normal": {"name": "X"}, "enemies": []}]
        guides = build_guides(ops, enemies, stages)
        assert len(guides) == 3
        assert guides[0]["title"] == "干员攻略_A"
        assert guides[1]["title"] == "敌人攻略_B"
        assert guides[2]["title"] == "关卡攻略_1-1_X"

    def test_empty_inputs(self):
        assert build_guides([], [], []) == []
