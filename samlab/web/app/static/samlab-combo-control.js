// Copyright 2018, National Technology & Engineering Solutions of Sandia, LLC
// (NTESS).  Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
// Government retains certain rights in this software.

define([
    "knockout",
    "knockout.mapping",
    ], function(ko, mapping)
{
    var component_name = "samlab-combo-control";
    ko.components.register(component_name,
    {
        viewModel:
        {
            createViewModel: function(params, component_info)
            {
                var component = mapping.fromJS({
                    current: params.current,
                    items: params.items,
                });

                component.current_label = ko.pureComputed(function()
                {
                    for(let item of component.items())
                    {
                        if(item.key() == component.current())
                        {
                            return item.label();
                        }
                    }
                });

                component.set_item = function(item)
                {
                    component.current(item.key());
                }

                return component;
            }
        },
        template: { require: "text!" + component_name + ".html" }
    });
});
