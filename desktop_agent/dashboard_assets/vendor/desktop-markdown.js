(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
    return;
  }
  root.DesktopAgentMarkdown = factory();
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  var SAFE_PROTOCOLS = new Set(["http:", "https:", "mailto:", "tel:"]);
  var MATH_COMMAND_SYMBOLS = {
    alpha: { tag: "mi", value: "\u03b1" },
    beta: { tag: "mi", value: "\u03b2" },
    gamma: { tag: "mi", value: "\u03b3" },
    delta: { tag: "mi", value: "\u03b4" },
    epsilon: { tag: "mi", value: "\u03b5" },
    theta: { tag: "mi", value: "\u03b8" },
    lambda: { tag: "mi", value: "\u03bb" },
    mu: { tag: "mi", value: "\u03bc" },
    pi: { tag: "mi", value: "\u03c0" },
    sigma: { tag: "mi", value: "\u03c3" },
    phi: { tag: "mi", value: "\u03c6" },
    psi: { tag: "mi", value: "\u03c8" },
    omega: { tag: "mi", value: "\u03c9" },
    Gamma: { tag: "mi", value: "\u0393" },
    Delta: { tag: "mi", value: "\u0394" },
    Theta: { tag: "mi", value: "\u0398" },
    Lambda: { tag: "mi", value: "\u039b" },
    Pi: { tag: "mi", value: "\u03a0" },
    Sigma: { tag: "mi", value: "\u03a3" },
    Phi: { tag: "mi", value: "\u03a6" },
    Psi: { tag: "mi", value: "\u03a8" },
    Omega: { tag: "mi", value: "\u03a9" },
    cdot: { tag: "mo", value: "\u22c5" },
    times: { tag: "mo", value: "\u00d7" },
    pm: { tag: "mo", value: "\u00b1" },
    mp: { tag: "mo", value: "\u2213" },
    leq: { tag: "mo", value: "\u2264" },
    geq: { tag: "mo", value: "\u2265" },
    neq: { tag: "mo", value: "\u2260" },
    approx: { tag: "mo", value: "\u2248" },
    infty: { tag: "mo", value: "\u221e" },
    partial: { tag: "mo", value: "\u2202" },
    nabla: { tag: "mo", value: "\u2207" },
    to: { tag: "mo", value: "\u2192" },
    leftarrow: { tag: "mo", value: "\u2190" },
    rightarrow: { tag: "mo", value: "\u2192" },
    sum: { tag: "mo", value: "\u2211" },
    prod: { tag: "mo", value: "\u220f" },
    int: { tag: "mo", value: "\u222b" },
    oint: { tag: "mo", value: "\u222e" },
    lim: { tag: "mi", value: "lim", normal: true },
    sin: { tag: "mi", value: "sin", normal: true },
    cos: { tag: "mi", value: "cos", normal: true },
    tan: { tag: "mi", value: "tan", normal: true },
    log: { tag: "mi", value: "log", normal: true },
    ln: { tag: "mi", value: "ln", normal: true },
    exp: { tag: "mi", value: "exp", normal: true },
    max: { tag: "mi", value: "max", normal: true },
    min: { tag: "mi", value: "min", normal: true }
  };
  var MATH_SPACING_COMMANDS = {
    ",": '<mspace width="0.167em"></mspace>',
    ";": '<mspace width="0.278em"></mspace>',
    ":": '<mspace width="0.222em"></mspace>',
    quad: '<mspace width="1em"></mspace>',
    qquad: '<mspace width="2em"></mspace>'
  };

  function normalizeSource(value) {
    return String(value == null ? "" : value).replace(/\r\n/g, "\n");
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function escapeAttribute(value) {
    return escapeHtml(value);
  }

  function escapeXml(value) {
    return escapeHtml(value);
  }

  function sanitizeUrl(rawUrl) {
    var value = String(rawUrl == null ? "" : rawUrl).trim();
    if (!value) return null;
    if (/^(#|\/(?!\/)|\.\/|\.\.\/)/.test(value)) {
      return value;
    }

    try {
      var parsed = new URL(value);
      if (SAFE_PROTOCOLS.has(parsed.protocol)) {
        return value;
      }
    } catch (_error) {
      return null;
    }

    return null;
  }

  function createTokenStore() {
    var values = [];
    return {
      put: function (html) {
        var index = values.push(String(html)) - 1;
        return "\u0000" + index + "\u0000";
      },
      restore: function (text) {
        return String(text).replace(/\u0000(\d+)\u0000/g, function (_match, rawIndex) {
          return values[Number(rawIndex)] || "";
        });
      },
    };
  }

  function matchSingleLineMathBlock(line) {
    var source = String(line == null ? "" : line).trim();
    var dollarMatch = source.match(/^\$\$([\s\S]+?)\$\$$/);
    if (dollarMatch) return dollarMatch[1].trim();
    var bracketMatch = source.match(/^\\\[([\s\S]+?)\\\]$/);
    if (bracketMatch) return bracketMatch[1].trim();
    return null;
  }

  function isMathFenceLine(line) {
    var source = String(line == null ? "" : line).trim();
    return source === "$$" || source === "\\[";
  }

  function mathFenceClosing(line) {
    var source = String(line == null ? "" : line).trim();
    if (source === "$$") return "$$";
    if (source === "\\[") return "\\]";
    return null;
  }

  function createMathState(source) {
    return {
      index: 0,
      source: String(source == null ? "" : source),
    };
  }

  function skipMathWhitespace(state) {
    while (state.index < state.source.length && /\s/.test(state.source[state.index])) {
      state.index += 1;
    }
  }

  function wrapMathNodes(nodes) {
    if (!nodes.length) return "<mrow></mrow>";
    if (nodes.length === 1) return nodes[0];
    return "<mrow>" + nodes.join("") + "</mrow>";
  }

  function wrapMathToken(tagName, value, options) {
    var config = options || {};
    var attrs = "";
    if (config.normal) {
      attrs += ' mathvariant="normal"';
    }
    return "<" + tagName + attrs + ">" + escapeXml(value) + "</" + tagName + ">";
  }

  function parseMathTextGroup(state) {
    skipMathWhitespace(state);
    if (state.index >= state.source.length) {
      return "<mtext></mtext>";
    }
    if (state.source[state.index] !== "{") {
      var start = state.index;
      while (state.index < state.source.length && !/\s/.test(state.source[state.index])) {
        state.index += 1;
      }
      return "<mtext>" + escapeXml(state.source.slice(start, state.index)) + "</mtext>";
    }
    state.index += 1;
    var depth = 1;
    var text = "";
    while (state.index < state.source.length && depth > 0) {
      var char = state.source[state.index];
      if (char === "{") {
        depth += 1;
        text += char;
      } else if (char === "}") {
        depth -= 1;
        if (depth > 0) {
          text += char;
        }
      } else {
        text += char;
      }
      state.index += 1;
    }
    return "<mtext>" + escapeXml(text) + "</mtext>";
  }

  function parseMathGroup(state) {
    skipMathWhitespace(state);
    if (state.index >= state.source.length) {
      return "<mrow></mrow>";
    }
    if (state.source[state.index] === "{") {
      state.index += 1;
      var nodes = parseMathExpression(state, "}");
      if (state.source[state.index] === "}") {
        state.index += 1;
      }
      return wrapMathNodes(nodes);
    }
    return parseMathPrimary(state);
  }

  function parseMathCommand(state) {
    state.index += 1;
    if (state.index >= state.source.length) {
      return wrapMathToken("mo", "\\");
    }

    var char = state.source[state.index];
    if (/[\\{}_^$]/.test(char)) {
      state.index += 1;
      return wrapMathToken("mo", char);
    }

    if (!/[A-Za-z]/.test(char)) {
      state.index += 1;
      if (Object.prototype.hasOwnProperty.call(MATH_SPACING_COMMANDS, char)) {
        return MATH_SPACING_COMMANDS[char];
      }
      return wrapMathToken("mo", char);
    }

    var start = state.index;
    while (state.index < state.source.length && /[A-Za-z]/.test(state.source[state.index])) {
      state.index += 1;
    }
    var command = state.source.slice(start, state.index);

    if (command === "frac") {
      var numerator = parseMathGroup(state);
      var denominator = parseMathGroup(state);
      return "<mfrac>" + numerator + denominator + "</mfrac>";
    }
    if (command === "sqrt") {
      return "<msqrt>" + parseMathGroup(state) + "</msqrt>";
    }
    if (command === "text" || command === "mathrm" || command === "mathbf") {
      return parseMathTextGroup(state);
    }
    if (command === "left" || command === "right") {
      skipMathWhitespace(state);
      if (state.index >= state.source.length) {
        return "";
      }
      var delimiter = state.source[state.index];
      state.index += 1;
      return wrapMathToken("mo", delimiter === "." ? "" : delimiter);
    }
    if (Object.prototype.hasOwnProperty.call(MATH_SPACING_COMMANDS, command)) {
      return MATH_SPACING_COMMANDS[command];
    }
    if (Object.prototype.hasOwnProperty.call(MATH_COMMAND_SYMBOLS, command)) {
      var symbol = MATH_COMMAND_SYMBOLS[command];
      return wrapMathToken(symbol.tag, symbol.value, { normal: symbol.normal });
    }

    return wrapMathToken("mi", command);
  }

  function parseMathAtom(state) {
    skipMathWhitespace(state);
    if (state.index >= state.source.length) {
      return "";
    }

    var char = state.source[state.index];
    if (char === "{") {
      state.index += 1;
      var nodes = parseMathExpression(state, "}");
      if (state.source[state.index] === "}") {
        state.index += 1;
      }
      return wrapMathNodes(nodes);
    }

    if (char === "\\") {
      return parseMathCommand(state);
    }

    if (/\d/.test(char)) {
      var digitStart = state.index;
      while (state.index < state.source.length && /[\d.]/.test(state.source[state.index])) {
        state.index += 1;
      }
      return wrapMathToken("mn", state.source.slice(digitStart, state.index));
    }

    if (/[A-Za-z]/.test(char)) {
      state.index += 1;
      return wrapMathToken("mi", char);
    }

    state.index += 1;
    if (char === "|" || char === "(" || char === ")" || char === "[" || char === "]") {
      return wrapMathToken("mo", char);
    }
    return wrapMathToken("mo", char);
  }

  function applyMathScripts(base, subscript, superscript) {
    if (subscript && superscript) {
      return "<msubsup>" + base + subscript + superscript + "</msubsup>";
    }
    if (subscript) {
      return "<msub>" + base + subscript + "</msub>";
    }
    if (superscript) {
      return "<msup>" + base + superscript + "</msup>";
    }
    return base;
  }

  function parseMathPrimary(state) {
    var base = parseMathAtom(state);
    if (!base) {
      return "";
    }

    var subscript = "";
    var superscript = "";
    while (state.index < state.source.length) {
      skipMathWhitespace(state);
      var marker = state.source[state.index];
      if (marker !== "_" && marker !== "^") {
        break;
      }
      state.index += 1;
      var value = parseMathGroup(state);
      if (marker === "_") {
        subscript = value || "<mrow></mrow>";
      } else {
        superscript = value || "<mrow></mrow>";
      }
    }

    return applyMathScripts(base, subscript, superscript);
  }

  function parseMathExpression(state, stopChar) {
    var nodes = [];
    while (state.index < state.source.length) {
      skipMathWhitespace(state);
      if (state.index >= state.source.length) break;
      if (stopChar && state.source[state.index] === stopChar) {
        break;
      }
      var node = parseMathPrimary(state);
      if (!node) {
        state.index += 1;
        continue;
      }
      nodes.push(node);
    }
    return nodes;
  }

  function renderMathFallback(mathSource, displayMode) {
    var mode = displayMode === "block" ? "block" : "inline";
    var tagName = mode === "block" ? "div" : "span";
    return (
      "<" +
      tagName +
      ' class="assistant-math assistant-math--' +
      escapeAttribute(mode) +
      ' assistant-math--fallback">' +
      '<code class="assistant-math-fallback">' +
      escapeHtml(mathSource) +
      "</code>" +
      "</" +
      tagName +
      ">"
    );
  }

  function renderMath(source, displayMode) {
    var mathSource = normalizeSource(source).trim();
    var mode = displayMode === "block" ? "block" : "inline";
    var tagName = mode === "block" ? "div" : "span";
    if (!mathSource) {
      return renderMathFallback("", mode);
    }

    try {
      var katex = typeof globalThis !== "undefined" ? globalThis.katex : null;
      if (katex && typeof katex.renderToString === "function") {
        return (
          "<" +
          tagName +
          ' class="assistant-math assistant-math--' +
          escapeAttribute(mode) +
          ' assistant-math--katex">' +
          katex.renderToString(mathSource, {
            displayMode: mode === "block",
            output: "html",
            strict: "ignore",
            throwOnError: true,
            trust: false
          }) +
          "</" +
          tagName +
          ">"
        );
      }
    } catch (_error) {
      return renderMathFallback(mathSource, mode);
    }

    return renderMathFallback(mathSource, mode);
  }

  function replaceInlineMath(source, tokens) {
    var result = "";
    for (var index = 0; index < source.length; index += 1) {
      var char = source[index];
      if (char === "\\" && source[index + 1] === "(") {
        var closeIndex = source.indexOf("\\)", index + 2);
        if (closeIndex > index + 2) {
          result += tokens.put(renderMath(source.slice(index + 2, closeIndex), "inline"));
          index = closeIndex + 1;
          continue;
        }
      }
      if (char === "$" && source[index + 1] !== "$") {
        var endIndex = index + 1;
        var found = false;
        while (endIndex < source.length) {
          var endChar = source[endIndex];
          if (endChar === "\n") break;
          if (endChar === "\\") {
            endIndex += 2;
            continue;
          }
          if (endChar === "$") {
            found = true;
            break;
          }
          endIndex += 1;
        }
        if (found && endIndex > index + 1) {
          result += tokens.put(renderMath(source.slice(index + 1, endIndex), "inline"));
          index = endIndex;
          continue;
        }
      }
      result += char;
    }
    return result;
  }

  function matchListLine(line) {
    var match = String(line).match(/^(\s*)([*+-]|\d+\.)\s+(.*)$/);
    if (!match) return null;
    return {
      indent: match[1].length,
      ordered: /\d+\./.test(match[2]),
      content: match[3],
    };
  }

  function isFenceStart(line) {
    return /^ {0,3}(```+|~~~+)/.test(line);
  }

  function isHeading(line) {
    return /^ {0,3}#{1,6}\s+/.test(line);
  }

  function isHorizontalRule(line) {
    return /^ {0,3}(?:[-*_])(?:\s*\1){2,}\s*$/.test(line);
  }

  function isBlockquoteLine(line) {
    return /^ {0,3}>\s?/.test(line);
  }

  function isTableDelimiter(line) {
    var cells = splitTableRow(line);
    if (!cells.length) return false;
    return cells.every(function (cell) {
      return /^:?-{3,}:?$/.test(cell);
    });
  }

  function looksLikeTableHeader(line) {
    return line.includes("|");
  }

  function isTableStart(lines, index) {
    if (index + 1 >= lines.length) return false;
    return looksLikeTableHeader(lines[index]) && isTableDelimiter(lines[index + 1]);
  }

  function startsBlock(lines, index) {
    if (index >= lines.length) return false;
    var line = lines[index];
    return (
      isFenceStart(line) ||
      isHeading(line) ||
      isHorizontalRule(line) ||
      isBlockquoteLine(line) ||
      isTableStart(lines, index) ||
      Boolean(matchListLine(line))
    );
  }

  function splitTableRow(line) {
    var source = String(line == null ? "" : line).trim();
    if (source.startsWith("|")) source = source.slice(1);
    if (source.endsWith("|")) source = source.slice(0, -1);

    var cells = [];
    var current = "";
    var escaping = false;
    for (var i = 0; i < source.length; i += 1) {
      var char = source[i];
      if (char === "\\" && !escaping) {
        escaping = true;
        current += char;
        continue;
      }
      if (char === "|" && !escaping) {
        cells.push(current.trim().replace(/\\\|/g, "|"));
        current = "";
        continue;
      }
      escaping = false;
      current += char;
    }

    cells.push(current.trim().replace(/\\\|/g, "|"));
    return cells;
  }

  function parseBlocks(markdown) {
    var source = normalizeSource(markdown);
    var lines = source.split("\n");
    var blocks = [];
    var index = 0;

    while (index < lines.length) {
      if (!lines[index].trim()) {
        index += 1;
        continue;
      }

      var singleLineMath = matchSingleLineMathBlock(lines[index]);
      if (singleLineMath != null) {
        blocks.push({
          type: "math",
          displayMode: "block",
          text: singleLineMath,
        });
        index += 1;
        continue;
      }

      if (isMathFenceLine(lines[index])) {
        var closingDelimiter = mathFenceClosing(lines[index]);
        var mathStartIndex = index;
        index += 1;
        var mathLines = [];
        while (index < lines.length && String(lines[index]).trim() !== closingDelimiter) {
          mathLines.push(lines[index]);
          index += 1;
        }
        if (index < lines.length) {
          index += 1;
          blocks.push({
            type: "math",
            displayMode: "block",
            text: mathLines.join("\n").trim(),
          });
          continue;
        }
        blocks.push({
          type: "paragraph",
          text: lines.slice(mathStartIndex).join("\n"),
        });
        break;
      }

      if (isFenceStart(lines[index])) {
        var fenceMatch = lines[index].match(/^ {0,3}((```+|~~~+))(.*)$/);
        var marker = fenceMatch[2][0];
        var fenceLength = fenceMatch[1].length;
        var language = String(fenceMatch[3] || "").trim().split(/\s+/)[0] || "";
        index += 1;
        var codeLines = [];
        while (index < lines.length) {
          var closingFence = new RegExp("^ {0,3}" + marker + "{" + fenceLength + ",}\\s*$");
          if (closingFence.test(lines[index])) break;
          codeLines.push(lines[index]);
          index += 1;
        }
        if (index < lines.length) index += 1;
        blocks.push({
          type: "code",
          language: language,
          text: codeLines.join("\n"),
        });
        continue;
      }

      if (isHeading(lines[index])) {
        var headingMatch = lines[index].match(/^ {0,3}(#{1,6})\s+(.*)$/);
        blocks.push({
          type: "heading",
          depth: headingMatch[1].length,
          text: headingMatch[2].trim(),
        });
        index += 1;
        continue;
      }

      if (isHorizontalRule(lines[index])) {
        blocks.push({ type: "hr" });
        index += 1;
        continue;
      }

      if (isBlockquoteLine(lines[index])) {
        var quoteLines = [];
        while (index < lines.length && isBlockquoteLine(lines[index])) {
          quoteLines.push(lines[index].replace(/^ {0,3}>\s?/, ""));
          index += 1;
        }
        blocks.push({
          type: "blockquote",
          text: quoteLines.join("\n"),
        });
        continue;
      }

      if (isTableStart(lines, index)) {
        var headerCells = splitTableRow(lines[index]);
        var alignmentCells = splitTableRow(lines[index + 1]).map(function (cell) {
          if (/^:-+:$/.test(cell)) return "center";
          if (/^-+:$/.test(cell)) return "right";
          return "left";
        });
        index += 2;
        var rows = [];
        while (index < lines.length && lines[index].trim() && looksLikeTableHeader(lines[index])) {
          rows.push(splitTableRow(lines[index]));
          index += 1;
        }
        blocks.push({
          type: "table",
          headers: headerCells,
          alignments: alignmentCells,
          rows: rows,
        });
        continue;
      }

      var listMatch = matchListLine(lines[index]);
      if (listMatch) {
        var ordered = listMatch.ordered;
        var baseIndent = listMatch.indent;
        var items = [];

        while (index < lines.length) {
          var currentMatch = matchListLine(lines[index]);
          if (!currentMatch || currentMatch.indent !== baseIndent || currentMatch.ordered !== ordered) break;

          var itemLines = [currentMatch.content];
          index += 1;

          while (index < lines.length) {
            if (!lines[index].trim()) {
              var nextLine = lines[index + 1] || "";
              var nextIndent = (nextLine.match(/^(\s*)/) || ["", ""])[1].length;
              if (nextLine.trim() && nextIndent > baseIndent && !matchListLine(nextLine)) {
                itemLines.push("");
                index += 1;
                continue;
              }
              break;
            }

            var nextMatch = matchListLine(lines[index]);
            var currentIndent = (lines[index].match(/^(\s*)/) || ["", ""])[1].length;
            if (nextMatch && nextMatch.indent === baseIndent && nextMatch.ordered === ordered) break;
            if (currentIndent > baseIndent) {
              itemLines.push(lines[index].slice(Math.min(lines[index].length, baseIndent + 2)));
              index += 1;
              continue;
            }
            break;
          }

          items.push(itemLines.join("\n").trimEnd());
        }

        blocks.push({
          type: "list",
          ordered: ordered,
          items: items,
        });
        continue;
      }

      var paragraphLines = [];
      while (index < lines.length && lines[index].trim() && !startsBlock(lines, index)) {
        paragraphLines.push(lines[index]);
        index += 1;
      }
      blocks.push({
        type: "paragraph",
        text: paragraphLines.join("\n"),
      });
    }

    return blocks;
  }

  function renderInline(text, options) {
    var config = options || {};
    var allowLinks = config.allowLinks !== false;
    var tokens = createTokenStore();
    var source = normalizeSource(text);

    source = source.replace(/`([^`\n]+)`/g, function (_match, code) {
      return tokens.put("<code>" + escapeHtml(code) + "</code>");
    });

    source = replaceInlineMath(source, tokens);

    if (allowLinks) {
      source = source.replace(/!\[([^\]\n]*)\]\(([^)\n]+)\)/g, function (match) {
        return tokens.put(escapeHtml(match));
      });

      source = source.replace(/\[([^\]\n]+)\]\(([^)\n]+)\)/g, function (_match, label, rawUrl) {
        var normalizedUrl = String(rawUrl).trim().replace(/\s+["'][^"']*["']\s*$/, "");
        var safeUrl = sanitizeUrl(normalizedUrl);
        if (!safeUrl) {
          return tokens.put(escapeHtml(label));
        }
        var linkLabel = renderInline(label, { allowLinks: false });
        return tokens.put(
          '<a href="' +
            escapeAttribute(safeUrl) +
            '" target="_blank" rel="noreferrer noopener">' +
            linkLabel +
            "</a>"
        );
      });

      source = source.replace(/\bhttps?:\/\/[^\s<]+/g, function (match) {
        var url = match;
        var trailing = "";
        while (/[),.;!?]$/.test(url)) {
          trailing = url.slice(-1) + trailing;
          url = url.slice(0, -1);
        }
        var safeUrl = sanitizeUrl(url);
        if (!safeUrl) return match;
        return (
          tokens.put(
            '<a href="' +
              escapeAttribute(safeUrl) +
              '" target="_blank" rel="noreferrer noopener">' +
              escapeHtml(url) +
              "</a>"
          ) + trailing
        );
      });
    }

    source = escapeHtml(source);
    source = source.replace(/~~(?=\S)([\s\S]*?\S)~~/g, "<del>$1</del>");
    source = source.replace(/\*\*\*(?=\S)([\s\S]*?\S)\*\*\*/g, "<strong><em>$1</em></strong>");
    source = source.replace(/___(?=\S)([\s\S]*?\S)___/g, "<strong><em>$1</em></strong>");
    source = source.replace(/\*\*(?=\S)([\s\S]*?\S)\*\*/g, "<strong>$1</strong>");
    source = source.replace(/__(?=\S)([\s\S]*?\S)__/g, "<strong>$1</strong>");
    source = source.replace(/(^|[^*])\*(?=\S)([\s\S]*?\S)\*(?!\*)/g, "$1<em>$2</em>");
    source = source.replace(/(^|[^_])_(?=\S)([\s\S]*?\S)_(?!_)/g, "$1<em>$2</em>");

    return tokens.restore(source);
  }

  function renderParagraphText(text) {
    return normalizeSource(text)
      .split("\n")
      .map(function (line) {
        return renderInline(line);
      })
      .join("<br />");
  }

  function renderListItem(text) {
    var blocks = parseBlocks(text);
    if (!blocks.length) return "";
    if (blocks.length === 1 && blocks[0].type === "paragraph") {
      return renderParagraphText(blocks[0].text);
    }
    return renderBlocks(blocks);
  }

  function renderBlocks(blocks) {
    return blocks
      .map(function (block) {
        if (block.type === "heading") {
          return "<h" + block.depth + ">" + renderInline(block.text) + "</h" + block.depth + ">";
        }
        if (block.type === "paragraph") {
          return "<p>" + renderParagraphText(block.text) + "</p>";
        }
        if (block.type === "math") {
          return '<div class="assistant-math-block">' + renderMath(block.text, "block") + "</div>";
        }
        if (block.type === "code") {
          var language = block.language ? ' data-language="' + escapeAttribute(block.language) + '"' : "";
          var label = block.language
            ? '<div class="assistant-code__label">' + escapeHtml(block.language) + "</div>"
            : "";
          return (
            '<div class="assistant-code">' +
            label +
            '<pre class="assistant-code__pre"><code' +
            language +
            ">" +
            escapeHtml(block.text) +
            "</code></pre></div>"
          );
        }
        if (block.type === "blockquote") {
          return "<blockquote>" + renderBlocks(parseBlocks(block.text)) + "</blockquote>";
        }
        if (block.type === "hr") {
          return "<hr />";
        }
        if (block.type === "list") {
          var listTag = block.ordered ? "ol" : "ul";
          return (
            "<" +
            listTag +
            ">" +
            block.items
              .map(function (item) {
                return "<li>" + renderListItem(item) + "</li>";
              })
              .join("") +
            "</" +
            listTag +
            ">"
          );
        }
        if (block.type === "table") {
          var head = block.headers
            .map(function (cell, index) {
              return (
                '<th class="assistant-table__cell assistant-table__cell--' +
                (block.alignments[index] || "left") +
                '">' +
                renderInline(cell) +
                "</th>"
              );
            })
            .join("");
          var rows = block.rows
            .map(function (row) {
              return (
                "<tr>" +
                block.headers
                  .map(function (_header, index) {
                    return (
                      '<td class="assistant-table__cell assistant-table__cell--' +
                      (block.alignments[index] || "left") +
                      '">' +
                      renderInline(row[index] || "") +
                      "</td>"
                    );
                  })
                  .join("") +
                "</tr>"
              );
            })
            .join("");
          return (
            '<div class="assistant-table"><table><thead><tr>' +
            head +
            "</tr></thead><tbody>" +
            rows +
            "</tbody></table></div>"
          );
        }
        return "<p>" + renderParagraphText(block.text || "") + "</p>";
      })
      .join("");
  }

  function render(markdown) {
    var blocks = parseBlocks(markdown);
    if (!blocks.length) return "";
    return renderBlocks(blocks);
  }

  function splitForStreaming(markdown) {
    var source = normalizeSource(markdown);
    if (!source) {
      return { committed: "", tail: "" };
    }

    var lines = source.match(/.*(?:\n|$)/g) || [];
    var offset = 0;
    var lastSafeIndex = 0;
    var openFence = null;
    var openMathFence = null;

    for (var i = 0; i < lines.length; i += 1) {
      var chunk = lines[i];
      if (!chunk) continue;
      var line = chunk.endsWith("\n") ? chunk.slice(0, -1) : chunk;
      var trimmed = line.trim();
      var fenceMatch = line.match(/^ {0,3}(```+|~~~+)/);

      if (!openFence && !openMathFence) {
        var closingFence = mathFenceClosing(trimmed);
        if (closingFence) {
          openMathFence = closingFence;
          offset += chunk.length;
          continue;
        }
      } else if (openMathFence) {
        if (trimmed === openMathFence) {
          openMathFence = null;
          lastSafeIndex = offset + chunk.length;
        }
        offset += chunk.length;
        continue;
      }

      if (fenceMatch) {
        var marker = fenceMatch[1][0];
        var length = fenceMatch[1].length;
        if (openFence && openFence.marker === marker && fenceMatch[1].length >= openFence.length) {
          openFence = null;
          lastSafeIndex = offset + chunk.length;
        } else if (!openFence) {
          openFence = { marker: marker, length: length };
        }
        offset += chunk.length;
        continue;
      }

      if (!openFence && !openMathFence && /^\s*$/.test(line)) {
        lastSafeIndex = offset + chunk.length;
      }

      offset += chunk.length;
    }

    if (!openFence && !openMathFence && /\n\n$/.test(source)) {
      lastSafeIndex = source.length;
    }

    return {
      committed: source.slice(0, lastSafeIndex),
      tail: source.slice(lastSafeIndex),
    };
  }

  function renderStreaming(markdown, options) {
    var config = options || {};
    var parts = splitForStreaming(markdown);
    var html = [];

    if (parts.committed.trim()) {
      html.push(render(parts.committed));
    }

    if (parts.tail || config.cursor) {
      if (parts.tail) {
        html.push(
          '<div class="assistant-tail"><pre class="assistant-tail__text">' +
            escapeHtml(parts.tail) +
            (config.cursor ? '<span class="assistant-copy__cursor" aria-hidden="true">▍</span>' : "") +
            "</pre></div>"
        );
      } else if (config.cursor) {
        html.push(
          '<p class="assistant-tail assistant-tail--cursor-only"><span class="assistant-copy__cursor" aria-hidden="true">▍</span></p>'
        );
      }
    }

    return html.join("");
  }

  function computeRevealChunkSize(remaining) {
    if (remaining > 1200) return 48;
    if (remaining > 600) return 28;
    if (remaining > 240) return 16;
    if (remaining > 80) return 8;
    return 4;
  }

  function advanceRevealContent(current, target) {
    var currentText = String(current == null ? "" : current);
    var targetText = String(target == null ? "" : target);
    if (currentText.length >= targetText.length) {
      return {
        content: targetText,
        done: true,
      };
    }

    var nextLength = currentText.length + computeRevealChunkSize(targetText.length - currentText.length);
    var nextContent = targetText.slice(0, nextLength);
    return {
      content: nextContent,
      done: nextContent.length >= targetText.length,
    };
  }

  return {
    advanceRevealContent: advanceRevealContent,
    escapeHtml: escapeHtml,
    render: render,
    renderStreaming: renderStreaming,
    sanitizeUrl: sanitizeUrl,
    splitForStreaming: splitForStreaming,
  };
});
