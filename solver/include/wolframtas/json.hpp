#pragma once

#include <cstdlib>
#include <cstddef>
#include <map>
#include <stdexcept>
#include <string>
#include <utility>
#include <variant>
#include <vector>

namespace wolframtas {

struct Json {
    using Array = std::vector<Json>;
    using Object = std::map<std::string, Json>;

    std::variant<std::nullptr_t, bool, double, std::string, Array, Object> value;

    const Object& object() const {
        if (const auto* object_value = std::get_if<Object>(&value)) {
            return *object_value;
        }
        throw std::runtime_error("expected JSON object");
    }

    const Array& array() const {
        if (const auto* array_value = std::get_if<Array>(&value)) {
            return *array_value;
        }
        throw std::runtime_error("expected JSON array");
    }

    const std::string& string() const {
        if (const auto* string_value = std::get_if<std::string>(&value)) {
            return *string_value;
        }
        throw std::runtime_error("expected JSON string");
    }

    double number() const {
        if (const auto* number_value = std::get_if<double>(&value)) {
            return *number_value;
        }
        throw std::runtime_error("expected JSON number");
    }
};

class JsonParser {
public:
    explicit JsonParser(std::string input) : input_(std::move(input)) {}

    Json parse() {
        Json value = parse_value();
        skip_ws();
        if (position_ != input_.size()) {
            throw std::runtime_error("unexpected trailing JSON input");
        }
        return value;
    }

private:
    Json parse_value() {
        skip_ws();
        if (position_ >= input_.size()) {
            throw std::runtime_error("unexpected end of JSON input");
        }
        const char ch = input_[position_];
        if (ch == '{') {
            return Json{parse_object()};
        }
        if (ch == '[') {
            return Json{parse_array()};
        }
        if (ch == '"') {
            return Json{parse_string()};
        }
        if (ch == '-' || (ch >= '0' && ch <= '9')) {
            return Json{parse_number()};
        }
        if (consume_literal("true")) {
            return Json{true};
        }
        if (consume_literal("false")) {
            return Json{false};
        }
        if (consume_literal("null")) {
            return Json{nullptr};
        }
        throw std::runtime_error("invalid JSON value");
    }

    Json::Object parse_object() {
        expect('{');
        Json::Object object;
        skip_ws();
        if (peek('}')) {
            expect('}');
            return object;
        }
        while (true) {
            skip_ws();
            const std::string key = parse_string();
            skip_ws();
            expect(':');
            object.emplace(key, parse_value());
            skip_ws();
            if (peek('}')) {
                expect('}');
                return object;
            }
            expect(',');
        }
    }

    Json::Array parse_array() {
        expect('[');
        Json::Array array;
        skip_ws();
        if (peek(']')) {
            expect(']');
            return array;
        }
        while (true) {
            array.push_back(parse_value());
            skip_ws();
            if (peek(']')) {
                expect(']');
                return array;
            }
            expect(',');
        }
    }

    std::string parse_string() {
        expect('"');
        std::string output;
        while (position_ < input_.size()) {
            const char ch = input_[position_++];
            if (ch == '"') {
                return output;
            }
            if (ch != '\\') {
                output.push_back(ch);
                continue;
            }
            if (position_ >= input_.size()) {
                throw std::runtime_error("unterminated JSON escape");
            }
            const char escaped = input_[position_++];
            switch (escaped) {
                case '"':
                case '\\':
                case '/':
                    output.push_back(escaped);
                    break;
                case 'b':
                    output.push_back('\b');
                    break;
                case 'f':
                    output.push_back('\f');
                    break;
                case 'n':
                    output.push_back('\n');
                    break;
                case 'r':
                    output.push_back('\r');
                    break;
                case 't':
                    output.push_back('\t');
                    break;
                default:
                    throw std::runtime_error("unsupported JSON string escape");
            }
        }
        throw std::runtime_error("unterminated JSON string");
    }

    double parse_number() {
        const char* start = input_.c_str() + position_;
        char* end = nullptr;
        const double value = std::strtod(start, &end);
        if (end == start) {
            throw std::runtime_error("invalid JSON number");
        }
        position_ = static_cast<std::size_t>(end - input_.c_str());
        return value;
    }

    void skip_ws() {
        while (position_ < input_.size()) {
            const char ch = input_[position_];
            if (ch != ' ' && ch != '\n' && ch != '\r' && ch != '\t') {
                break;
            }
            ++position_;
        }
    }

    bool consume_literal(const std::string& literal) {
        if (input_.compare(position_, literal.size(), literal) != 0) {
            return false;
        }
        position_ += literal.size();
        return true;
    }

    bool peek(char expected) const {
        return position_ < input_.size() && input_[position_] == expected;
    }

    void expect(char expected) {
        skip_ws();
        if (position_ >= input_.size() || input_[position_] != expected) {
            throw std::runtime_error(std::string("expected JSON character: ") + expected);
        }
        ++position_;
    }

    std::string input_;
    std::size_t position_ = 0;
};

} // namespace wolframtas
