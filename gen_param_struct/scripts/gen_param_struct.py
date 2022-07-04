#!/usr/bin/env python3

import yaml
import sys
import os


# class to help minimize string copies
class Buffer:
    def __init__(self):
        self.data_ = bytearray()

    def __iadd__(self, element):
        self.data_.extend(element.encode())
        return self

    def __str__(self):
        return self.data_.decode()


# class used to fill template.txt using passed in yaml file
class GenParamStruct:

    def __init__(self):
        self.contents = ""
        self.struct = Buffer()
        self.param_set = Buffer()
        self.param_declare = Buffer()
        self.target = ""

    def parse_params(self, name, value, nested_name_list):

        nested_name = "".join(x + "_." for x in nested_name_list[1:])

        default_value = value['default_value']

        if isinstance(default_value, list):
            if isinstance(default_value[0], str):
                data_type = "std::string"
                conversion_func = "as_string_array()"

                def str_fun(s):
                    return "\"%s\"" % s
            elif isinstance(default_value[0], float):
                data_type = "double"
                conversion_func = "as_double_array()"

                def str_fun(s):
                    return str(s)
            elif isinstance(default_value[0], int) and not isinstance(default_value[0], bool):
                data_type = "int"
                conversion_func = "as_integer_array()"

                def str_fun(s):
                    return str(s)
            elif isinstance(default_value[0], bool):
                data_type = "bool"
                conversion_func = "as_bool_array()"

                def str_fun(cond):
                    return "true" if cond else "false"
            else:
                sys.stderr.write("invalid yaml type: %s" % type(default_value[0]))
                raise AssertionError()

            self.struct += "std::vector<%s> %s_ = {" % (data_type, name)
            for ind, val in enumerate(default_value[:-1]):
                self.struct += "%s, " % str_fun(val)
            self.struct += "%s};\n" % str_fun(default_value[-1])

        else:
            if isinstance(default_value, str):
                data_type = "std::string"
                conversion_func = "as_string()"

                def str_fun(s):
                    return "\"%s\"" % s
            elif isinstance(default_value, float):
                data_type = "double"
                conversion_func = "as_double()"

                def str_fun(s):
                    return str(s)
            elif isinstance(default_value, int) and not isinstance(default_value, bool):
                data_type = "int"
                conversion_func = "as_int()"

                def str_fun(s):
                    return str(s)
            elif isinstance(default_value, bool):
                data_type = "bool"
                conversion_func = "as_bool()"

                def str_fun(cond):
                    return "true" if cond else "false"
            else:
                sys.stderr.write("invalid yaml type: %s" % type(default_value))
                raise AssertionError()

            self.struct += "%s %s_ = %s;\n" % (data_type, name, str_fun(default_value))

        param_prefix = "p_"
        param_prefix += "".join(x + "_" for x in nested_name_list[1:])
        param_name = "".join(x + "." for x in nested_name_list[1:]) + name

        self.param_set += "if (param.get_name() == " + "\"%s\") {\n" % param_name
        self.param_set += "params_.%s_ = param.%s;\n" % (nested_name + name, conversion_func)
        self.param_set += "}\n"

        self.param_declare += "if (!parameters_interface->has_parameter(\"%s\")){\n" % param_name
        self.param_declare += "auto %s = rclcpp::ParameterValue(params_.%s_);\n" % (param_prefix + name, nested_name + name)
        self.param_declare += "parameters_interface->declare_parameter(\"%s\", %s);\n" % (
            param_name, param_prefix + name)
        self.param_declare += "} else {\n"
        self.param_declare += "params_.%s_ = parameters_interface->get_parameter(\"%s\").%s;" % (
        nested_name + name, param_name, conversion_func)

        self.param_declare += "}\n"

    def parse_dict(self, name, root_map, nested_name):
        if isinstance(root_map, dict):
            if name != self.target:
                self.struct += "struct %s {\n" % name
            for key in root_map:
                if isinstance(root_map[key], dict):
                    nested_name.append(name)
                    self.parse_dict(key, root_map[key], nested_name)
                    nested_name.pop()
                else:
                    self.parse_params(name, root_map, nested_name)
                    break


            if name != self.target:
                self.struct += "} %s_;\n" % name
        # else:
            # self.parse_params(name, root_map, nested_name)

    def run(self):

        param_gen_directory = sys.argv[0].split("/")
        param_gen_directory = "".join(x + "/" for x in param_gen_directory[:-1])

        out_directory = sys.argv[1]
        if out_directory[-1] != "/":
            out_directory += "/"
        if param_gen_directory[-1] != "/":
            param_gen_directory += "/"

        if not os.path.isdir(out_directory):
            sys.stderr.write("The specified output directory: %s does not exist" % out_directory)
            raise AssertionError()

        yaml_file = sys.argv[2]
        self.target = sys.argv[3]

        with open(yaml_file) as f:
            docs = yaml.load_all(f, Loader=yaml.FullLoader)
            if len(sys.argv) != 4:
                sys.stderr.write("generate_param_struct_header expects four input argument: target, output directory, "
                                 "yaml file path, and yaml root name")
                raise AssertionError()

            doc = list(docs)[0]
            if len(doc) != 1:
                sys.stderr.write("the controller yaml definition must only have one root element")
                raise AssertionError()
            # doc = docs[0]
            # for doc in docs:
                # for k, v in doc.items():
                #     if k == self.target:
            self.parse_dict(self.target, doc, [])

        COMMENTS = "// this is auto-generated code "
        INCLUDES = "#include <rclcpp/node.hpp>\n#include <vector>\n#include <string>"
        NAMESPACE = self.target + "_parameters"

        with open(param_gen_directory + "/templates/template.txt", "r") as f:
            self.contents = f.read()

        self.contents = self.contents.replace("**COMMENTS**", COMMENTS)
        self.contents = self.contents.replace("**INCLUDES**", INCLUDES)
        self.contents = self.contents.replace("**NAMESPACE**", NAMESPACE)
        self.contents = self.contents.replace("**STRUCT_NAME**", str(self.target))
        self.contents = self.contents.replace("**STRUCT_CONTENT**", str(self.struct))
        self.contents = self.contents.replace("**PARAM_SET**", str(self.param_set))
        self.contents = self.contents.replace("**DECLARE_PARAMS**", str(self.param_declare))

        with open(out_directory + self.target + ".h", "w") as f:
            f.write(self.contents)


if __name__ == "__main__":
    gen_param_struct = GenParamStruct()
    gen_param_struct.run()

