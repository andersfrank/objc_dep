#!/usr/bin/python

# Nicolas Seriot
# 2011-01-06 -> 2011-12-16
# https://github.com/nst/objc_dep/

"""
Input: path of an Objective-C project

Output: import dependencies Graphviz format

Typical usage: $ python objc_dep.py /path/to/project [-x regex] [-i subfolder [subfolder ...]] > graph.dot

The .dot file can be opened with Graphviz or OmniGraffle.

- red arrows: .pch imports
- blue arrows: two ways imports
"""

import sys
import os
from sets import Set
import re
from os.path import basename
import argparse

local_regex_import = re.compile("^\s*#(?:import|include)\s+\"(?P<filename>\S*)(?P<extension>\.(?:h|hpp|hh))?\"")
system_regex_import = re.compile("^\s*#(?:import|include)\s+[\"<](?P<filename>\S*)(?P<extension>\.(?:h|hpp|hh))?[\">]")

def gen_filenames_imported_in_file(path, regex_exclude, system, extensions):
    for line in open(path):
        results = re.search(system_regex_import, line) if system else re.search(local_regex_import, line)
        if results:
            filename = results.group('filename')
            extension = results.group('extension')
            if regex_exclude is not None and regex_exclude.search(filename + extension):
                continue
            yield (filename + extension) if extension else filename

def dependencies_in_project(path, ext, exclude, ignore, system, extensions):
    d = {}
    
    regex_exclude = None
    if exclude:
        regex_exclude = re.compile(exclude)
    
    for root, dirs, files in os.walk(path):

        if ignore:
            for subfolder in ignore:
                if subfolder in dirs:
                    dirs.remove(subfolder)

        objc_files = (f for f in files if f.endswith(ext))

        for f in objc_files:
            
            filename = f if extensions else os.path.splitext(f)[0]
            if regex_exclude is not None and regex_exclude.search(filename):
                continue

            if filename not in d:
                d[filename] = Set()
            
            path = os.path.join(root, f)

            for imported_filename in gen_filenames_imported_in_file(path, regex_exclude, system, extensions):
                if imported_filename != filename and '+' not in imported_filename and '+' not in filename:
                    imported_filename = imported_filename if extensions else os.path.splitext(imported_filename)[0]
                    d[filename].add(imported_filename)

    return d

def dependencies_in_project_with_file_extensions(path, exts, exclude, ignore, system, extensions):

    d = {}
    
    for ext in exts:
        d2 = dependencies_in_project(path, ext, exclude, ignore, system, extensions)
        for (k, v) in d2.iteritems():
            if not k in d:
                d[k] = Set()
            d[k] = d[k].union(v)

    return d

def bidirectional_files(d):

    two_ways = Set()

    # d is {'a1':[b1, b2], 'a2':[b1, b3, b4], ...}

    for a, l in d.iteritems():
        for b in l:
            if b in d and a in d[b]:
                if (a, b) in two_ways or (b, a) in two_ways:
                    continue
                if a != b:
                    two_ways.add((a, b))
                    
    return two_ways

def leaf_files(d):

    dead_ends = Set()

    for file_a, file_a_dependencies in d.iteritems():
        for file_b in file_a_dependencies:
            if not file_b in dead_ends and not file_b in d:
                dead_ends.add(file_b)

    return dead_ends

def files_containing_type(d,type_name):

    viewModels = Set()

    for file_a, file_a_dependencies in d.iteritems():
        add_class_with_name_to_set(viewModels,file_a,type_name)
        for file_b in file_a_dependencies:
            add_class_with_name_to_set(viewModels,file_b,type_name)
    return viewModels

def add_class_with_name_to_set(the_set,class_name,type_name):
    if not class_name in the_set and type_name in class_name:
        the_set.add(class_name)

def category_files(d):
    d2 = {}
    l = []
    
    for k, v in d.iteritems():
        if not v and '+' in k:
            l.append(k)
        else:
            d2[k] = v

    return l, d2

def referenced_classes_from_dict(d):
    d2 = {}

    for k, deps in d.iteritems():
        for x in deps:
            d2.setdefault(x, Set())
            d2[x].add(k)
    
    return d2
    
def print_frequencies_chart(d):
    
    lengths = map(lambda x:len(x), d.itervalues())
    if not lengths: return
    max_length = max(lengths)
    
    for i in range(0, max_length+1):
        s = "%2d | %s\n" % (i, '*'*lengths.count(i))
        sys.stderr.write(s)

    sys.stderr.write("\n")
    
    l = [Set() for i in range(max_length+1)]
    for k, v in d.iteritems():
        l[len(v)].add(k)

    for i in range(0, max_length+1):
        s = "%2d | %s\n" % (i, ", ".join(sorted(list(l[i]))))
        sys.stderr.write(s)

def append_ignore(ignore,l):
    if ignore:
        l.append("\t")
        l.append("\tnode [shape=box, color=blue];")
        l.append("\t\"Ignored\" [label=\"%s\"];" % "\\n".join(ignore))

def append_category_list(category_list,l):
    if category_list:
        l.append("\t")
        l.append("\tedge [color=black];")
        l.append("\tnode [shape=plaintext];")
        l.append("\t\"Categories\" [label=\"%s\"];" % "\\n".join(category_list))
 
def append_leafs(leafs,l):
    l.append("\t")
    for k in leafs:
        shape = "box"
        # sys.stderr.write()
        if "ViewModel" in k:
            shape = "oval"
        l.append("\t\"%s\" [color=gray, style=dashed, fontcolor=gray shape=%s]" % (k,shape))

def append_style(view_models,l,color,shape,fontcolor):
    l.append("\t")
    for k in view_models:
            l.append("\t\"%s\" [shape=%s fillcolor=%s style=filled fontcolor=%s]" % (k,shape,color,fontcolor))

def append_ananymous_style(classes,l):
    l.append("\t")
    for k in classes:
            l.append("\t\"%s\" [shape=box fillcolor=gray style=dashed]" % k)

def append_biderectional_classes(bidirectional_classes,l):
    l.append("\t")
    l.append("\tedge [color=black, dir=both];")

    for (k, k2) in bidirectional_classes:
        l.append("\t\"%s\" -> \"%s\";" % (k, k2))


def append_pch(pch_set,l):
    l.append("\t")
    
    for (k, v) in pch_set.iteritems():
        l.append("\t\"%s\" [color=red];" % k)
        for x in v:
            l.append("\t\"%s\" -> \"%s\" [color=red];" % (k, x))

def append_unidirectional_classes(d,bidirectional_set,l):
    
    l.append("\tnode [shape=box style=rounded];")
    l.append("\tedge [color=gray60];")

    for k, deps in d.iteritems():
        if deps:
            deps.discard(k)
        
        if len(deps) == 0:
            l.append("\t\"%s\" -> {};" % (k))
        
        for k2 in deps:
            if not ((k, k2) in bidirectional_set or (k2, k) in bidirectional_set):
                l.append("\t\"%s\" -> \"%s\";" % (k, k2))

def dependencies_in_dot_format(path, exclude, ignore, system, extensions):
    
    d = dependencies_in_project_with_file_extensions(path, ['.h', '.hh', '.hpp', '.m', '.mm', '.c', '.cc', '.cpp'], exclude, ignore, system, extensions)
    bidirectional_files_set = bidirectional_files(d)
    leafs = leaf_files(d)
    category_list, d = category_files(d)
    pch_set = dependencies_in_project(path, '.pch', exclude, ignore, system, extensions)

    l = []
    l.append("digraph G {")
    append_unidirectional_classes(d,bidirectional_files_set,l)
    append_pch(pch_set,l)
    append_biderectional_classes(bidirectional_files_set,l)
    append_style(files_containing_type(d,"ViewController"),l,"gray10","box","white")
    append_style(files_containing_type(d,"ViewModel"),l,"gray85","oval","black")
    append_category_list(category_list,l)
    append_ignore(ignore,l)
    l.append("}\n")

    return '\n'.join(l)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-x", "--exclude", nargs='?', default='' ,help="regular expression of substrings to exclude from module names")
    parser.add_argument("-i", "--ignore", nargs='*', help="list of subfolder names to ignore")
    parser.add_argument("-s", "--system", action='store_true', default=False, help="include system dependencies")
    parser.add_argument("-e", "--extensions", action='store_true', default=False, help="print file extensions")
    parser.add_argument("project_path", help="path to folder hierarchy containing Objective-C files")
    args= parser.parse_args()

    print dependencies_in_dot_format(args.project_path, args.exclude, args.ignore, args.system, args.extensions)

if __name__=='__main__':
    main()
